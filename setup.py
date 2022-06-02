# ref: https://towardsdatascience.com/create-and-publish-your-own-python-package-ea45bee41cdc
import setuptools

# Reads the content of your README.md into a variable to be used in the setup below
with open("README.rst", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    download_url="https://github.com/iapyeh/sshscript/archive/refs/tags/0.94.tar.gz",
    name='sshscript',                           # should match the package folder
    packages=['sshscript'],                     # should match the package folder
    license='MIT',                                  # should match your chosen license
    long_description=long_description,           
    long_description_content_type="text/x-rst",  
    author='Hsin Yuan Yeh',
    author_email='iapyeh@gmail.com',
    url='https://github.com/iapyeh/sshscript', 
    project_urls = {                                # Optional
        "Bug Tracker": "https://github.com/iapyeh/sshscript/issues"
    },
    install_requires=['paramiko'],                  # list all packages that your package uses
    keywords=["pypi", "sshscript", "ssh", "paramiko", "subprocess","shell script"], #descriptive meta-data
    classifiers=[                                   # https://pypi.org/classifiers
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Documentation',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    entry_points='''
        [console_scripts]
        sshscript=sshscript.sshscript:run
    ''',    
)