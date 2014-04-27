from setuptools import setup, find_packages
setup(
    name = "sioworkers",
    version = '1.1',    # TODO: bump version when new protocol is done
    author = "SIO2 Project Team",
    author_email = 'sio2@sio2project.mimuw.edu.pl',
    description = "Programming contest judging infrastructure",
    url = 'https://github.com/sio2project/sioworkers',
    license = 'GPL',

    # we need twisted.plugins in packages to install the sio twisted command
    packages = find_packages() + ['twisted.plugins'],
    namespace_packages = ['sio', 'sio.compilers', 'sio.executors'],

    install_requires = [
        'filetracker>=0.96',
        'simplejson',
        'Celery>=3.1.15',
        'Twisted',
        'enum34',  # backport from py3
    ],

    setup_requires = [
        'nose',
        'enum34',
    ],

    entry_points = {
        'sio.jobs': [
            'ping = sio.workers.ping:run',
            'compile = sio.compilers.job:run',
            'exec = sio.executors.executor:run',
            'vcpu-exec = sio.executors.vcpu_exec:run',
            'cpu-exec = sio.executors.executor:run',
            'unsafe-exec = sio.executors.unsafe_exec:run',
            'ingen = sio.executors.ingen:run',
            'inwer = sio.executors.inwer:run',
        ],
        'sio.compilers': [
            # Example compiler:
            'foo = sio.compilers.template:run',

            # Default extension compilers:
            'default-c = sio.compilers.gcc:run_default_c',
            'default-cc = sio.compilers.gcc:run_default_cpp',
            'default-cpp = sio.compilers.gcc:run_default_cpp',
            'default-pas = sio.compilers.fpc:run_default',
            'default-java = sio.compilers.java:run_default',

            # Sandboxed compilers:
            'c = sio.compilers.gcc:run_gcc',
            'gcc = sio.compilers.gcc:run_gcc',

            'cc = sio.compilers.gcc:run_gplusplus',
            'cpp = sio.compilers.gcc:run_gplusplus',
            'g++ = sio.compilers.gcc:run_gplusplus',

            'pas = sio.compilers.fpc:run',
            'fpc = sio.compilers.fpc:run',

            'java = sio.compilers.java:run',

            # Non-sandboxed compilers
            'system-c = sio.compilers.system_gcc:run_gcc',
            'system-gcc = sio.compilers.system_gcc:run_gcc',

            'system-cc = sio.compilers.system_gcc:run_gplusplus',
            'system-cpp = sio.compilers.system_gcc:run_gplusplus',
            'system-g++ = sio.compilers.system_gcc:run_gplusplus',

            'system-pas = sio.compilers.system_fpc:run',
            'system-fpc = sio.compilers.system_fpc:run',

            'system-java = sio.compilers.system_java:run',
        ],
        'console_scripts': [
            'sio-batch = sio.workers.runner:main',
            'sio-run-filetracker = sio.workers.ft:launch_filetracker_server',
            'sio-get-sandbox = sio.workers.sandbox:main',
            'sio-compile = sio.compilers.job:main',
            'sio-celery-worker = sio.celery.worker:main',
        ]
    }
)


# Make Twisted regenerate the dropin.cache, if possible.  This is necessary
# because in a site-wide install, dropin.cache cannot be rewritten by
# normal users.
try:
    from twisted.plugin import IPlugin, getPlugins
except ImportError:
    pass
else:
    list(getPlugins(IPlugin))
