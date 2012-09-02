from setuptools import setup, find_packages
setup(
    name = "sioworkers",
    version = '0.9',
    author = "SIO2 Project Team",
    author_email = 'sio2@sio2project.mimuw.edu.pl',
    description = "Programming contest judging infrastructure",
    url = 'https://github.com/sio2project/sioworkers',
    license = 'GPL',

    packages = find_packages(),
    namespace_packages = ['sio', 'sio.compilers', 'sio.executors'],

    install_requires = [
        'filetracker>=0.95',
        'simplejson',
        'Celery',
    ],

    entry_points = {
        'sio.jobs': [
            'ping = sio.workers.ping:run',
            'compile = sio.compilers.job:run',
            'exec = sio.executors.executor:run',
            'vcpu-exec = sio.executors.vcpu_exec:run',
            'unsafe-exec = sio.executors.unsafe_exec:run',
        ],
        'sio.compilers': [
            # Example compiler:
            'foo = sio.compilers.template:run',

            # Default extension compilers:
            'default-c = sio.compilers.gcc:run_default_c',
            'default-cc = sio.compilers.gcc:run_default_cpp',
            'default-cpp = sio.compilers.gcc:run_default_cpp',
            'default-pas = sio.compilers.fpc:run_default',

            # Sandboxed compilers:
            'c = sio.compilers.gcc:run_gcc',
            'gcc = sio.compilers.gcc:run_gcc',

            'cpp = sio.compilers.gcc:run_gplusplus',
            'g++ = sio.compilers.gcc:run_gplusplus',

            'pas = sio.compilers.fpc:run',
            'fpc = sio.compilers.fpc:run',

            # Non-sandboxed compilers
            'system-c = sio.compilers.system_gcc:run_gcc',
            'system-gcc = sio.compilers.system_gcc:run_gcc',

            'system-cpp = sio.compilers.system_gcc:run_gplusplus',
            'system-g++ = sio.compilers.system_gcc:run_gplusplus',

            'system-pas = sio.compilers.system_fpc:run',
            'system-fpc = sio.compilers.system_fpc:run',
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

