from setuptools import setup, find_packages 

setup(
    name='EnvriProvTemplates',
    version='0.2.1',
    author="Stephan Kindermann, Doron Goldfarb",
    author_email="kindermann@dkrz.de, Doron.Goldfarb@umweltbundesamt.at",
    packages=['provtemplates',],
    url="https://github.com/EnvriPlus-PROV/EnvriProvTemplates",
    scripts=['bin/expandTemplate.py'],
    license='Creative Commons Attribution-Noncommercial-Share Alike license',
    long_description=open('README.md').read(),
)
