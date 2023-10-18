##
## This script is modified from:
## https://github.com/rushter/socks5/blob/master/server.py
## It is part of https://github.com/rushter/socks5
##
import select
import socket
import struct
import traceback
import threading
SOCKS_VERSION = 5
from logging import DEBUG

class SocksProxy():
    def __init__(self,transport,username=None,password=None,logger=None) -> None:
        self.transport = transport
        self.username = username
        self.password = password
        self.logger = logger
    def log(self,msg):
        if self.logger: self.logger.log(DEBUG,msg)
    def close(self):
        self.connection.close()
    def handle(self,channel):
        #logging.info('Accepting connection from %s:%s' % self.client_address)
        self.connection = channel
        # greeting header
        # read and unpack 2 bytes from a client
        header = self.connection.recv(2)
        version, nmethods = struct.unpack("!BB", header)
        try:
            # socks 5
            assert version == SOCKS_VERSION
            assert nmethods > 0

            # get available methods
            methods = self.get_available_methods(nmethods)

            ## send welcome message
            self.connection.sendall(struct.pack("!BB", SOCKS_VERSION, 2 if self.username else 0))

            if self.username:
                ## accept only USERNAME/PASSWORD auth
                if 2 not in set(methods):
                    self.close()
                    return
                if not self.verify_credentials():
                    return

            # request
            version, cmd, _, address_type = struct.unpack("!BBBB", self.connection.recv(4))

            if address_type == 1:  # IPv4
                address = socket.inet_ntoa(self.connection.recv(4))
            elif address_type == 3:  # Domain name
                domain_length = self.connection.recv(1)[0]
                address = self.connection.recv(domain_length)
                address = socket.gethostbyname(address)
            else:
                address = None
            port = struct.unpack('!H', self.connection.recv(2))[0]
            assert address, f'no address, address_type={address_type},cmd={cmd},versio={version}'
        except:
            self.log(traceback.format_exc())
            self.close()
            return

        # reply
        try:
            if cmd == 1:  # CONNECT
                remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                remote.connect((address, port))
                bind_address = remote.getsockname()
                self.log('Connected to %s %s' % (address, port))
            else:
                self.close()

            addr = struct.unpack("!I", socket.inet_aton(bind_address[0]))[0]
            port = bind_address[1]
            reply = struct.pack("!BBBBIH", SOCKS_VERSION, 0, 0, 1,
                                addr, port)

        except Exception as err:
            self.log(traceback.format_exc())
            # return connection refused error
            reply = self.generate_failed_reply(address_type, 5)

        self.connection.sendall(reply)

        # establish data exchange
        if reply[1] == 0 and cmd == 1:
            self.exchange_loop(self.connection, remote)

        self.close()

    def get_available_methods(self, n):
        methods = []
        for i in range(n):
            methods.append(ord(self.connection.recv(1)))
        return methods

    def verify_credentials(self):

        version = ord(self.connection.recv(1))
        assert version == 1

        username_len = ord(self.connection.recv(1))
        username = self.connection.recv(username_len).decode('utf-8')

        password_len = ord(self.connection.recv(1))
        password = self.connection.recv(password_len).decode('utf-8')

        if (username == self.username and password == self.password):
            # success, status = 0
            response = struct.pack("!BB", version, 0)
            self.connection.sendall(response)
            self.log('authentication passed')
            return True

        # failure, status != 0
        response = struct.pack("!BB", version, 0xFF)
        self.connection.sendall(response)
        self.server.close_request(self.request)
        self.log('authentication failure')
        return False

    def generate_failed_reply(self, address_type, error_number):
        return struct.pack("!BBBBIH", SOCKS_VERSION, error_number, 0, address_type, 0, 0)

    def exchange_loop(self, client, remote):

        while True:

            # wait until client or remote is available for read
            r, w, e = select.select([client, remote], [], [])

            if client in r:
                data = client.recv(4096)
                if remote.send(data) <= 0:
                    break

            if remote in r:
                data = remote.recv(4096)
                if client.send(data) <= 0:
                    break

class ThreadingSocksProxy(object):
    def __init__(self, transport,remote_port,username=None,password=None,logger=None) -> None:
        self.transport = transport
        self.remote_port = remote_port
        self.username = username
        self.password = password
        self.logger = logger
    def start(self):
        def task():
            global SocksProxy
            while self.transport.is_active():
                chan = self.transport.accept(1)
                if chan is None: continue
                sp = SocksProxy(self.transport,self.username,self.password,self.logger)
                thr = threading.Thread(
                    target=sp.handle,args=(chan,)
                )
                thr.setDaemon(True)
                thr.start()
        self.transport.request_port_forward("127.0.0.1", self.remote_port)
        thr = threading.Thread(target=task)
        thr.setDaemon(True)
        thr.start()
        return thr