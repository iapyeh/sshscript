# SSHScript vs. Ansible

Last Updated on 2023/11/4

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>


## What is Similar Between SSHScript and Ansible?

- Both SSHScript and Ansible are Python packages.
- Both can be used to automate system operations.
- Both can serve as alternatives to traditional shell scripts.
- Neither requires deployment of agents or clients on remote servers.

## How is SSHScript Different from Ansible?

- SSHScript relies on Python scripts, while Ansible employs YAML for configuration.SSHScript users write Python scripts, while Ansible users write YAML.
- Learning Python for SSHScript has universal applicability for various tasks, whereas Ansible YAML skills are specific to Ansible. If you already know how to write Python, you don't need to learn any new skills. All you need to do is learn about what SSHScript brings to you. While Ansible is a whole new paradigm with many unfamiliar terms that are rarely seen by programmers.
- SSHScript users can leverage Python's powerful features, including threading, for creating efficient and adaptable scripts. 
- SSHScript can be integrated into existing Python projects, while Ansible is a standalone tool. This means that SSHScript can be used to automate Ansible, and Ansible can run scripts written in SSHScript.
- SSHScript allows users to tap into Python's extensive ecosystem, making any Python package accessible without waiting for an Ansible module to be developed.
- SSHScript provides transparency in system execution, allowing users to precisely understand system changes during the process, while Ansible's playbook/module actions can seem like a black box, making SSHScript easier to debug and offering enhanced security.

## Quotes
By [Châu Hồng Lĩnh](https://www.facebook.com/chauhonglinh2021), 2023/11/10 ([Facebook Comments](https://www.facebook.com/nixcraft/posts/pfbid0DjJ1pyzVqbUuXNLjEjYjvGSRGi9tQNdQ3oDKnKGNrVDCZcAxDFsQqugVUe3BCK3tl?comment_id=650843943738861))
>know several companies in the U.S., from huge corporations to small, medium and startups, at the beginning, they were very happy with Kubernetes, SRE fancy stuffs. After awhile, they confessed that the biggest mistake they had ever made was using Kubernetes 😃

>>(Early around 2014, Châu Hồng Lĩnh has developed [an excellent Ruby project](https://bitbucket.org/linhchauatl/run_commands/src/master/) which runs arbitrary list of commands on a list of servers from a single machine. )