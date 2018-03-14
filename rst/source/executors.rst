Executors
=========

This package provides several SIO Workers jobs, which can be used
to run arbitrary binary programs under a supervisor program in a secure way.

These jobs also allows to check the correctness of the output produced by the
program, either using the default ``compare`` program distributed in an
appropriate sandbox, or by using an external checker provided by the user.

Job parameters
--------------

The following parameters are recognized in ``environ``:

  ``exe_file``
    Filetracker path of the binary to run.

  ``in_file``
    Filetracker path of the file to be passed to program's stdin.

  ``out_file``
    (optional) Filetracker path where the output produced by the program will
    be saved.

  ``upload_out``
    Should the ``out_file`` be uploaded to the Filetracker remote store?
    If ``False``, then the file is only stored in the Filetracker local cache.

    Ignored if no ``out_file`` is specified.

    Default: ``False``

  ``exec_mem_limit``
    Memory limit in kB.

    Default: 66000 kB

  ``exec_time_limit``
    Time limit in milliseconds.

    Default: 30 sec.

  ``exec_out_limit``
    Program output limit in bytes.

    Default: 50 MB

  ``check_output``
    Should the program output be checked?

    The output is checked only if no error was reported by the supervisor,
    i.e. the program terminated with exit code 0, obeying the resource limits.

    Default: ``False``

  ``hint_file``
    Filetracker path of the model output file for the checker. Mandatory if
    ``check_output`` is ``True``.

  ``chk_file``
    Filetracker path of the output checker binary. See :ref:`output-checker`.

    Default: ``compare`` program from the sandbox.

  ``untrusted_checker``
    Pass ``True`` to run ``chk_file`` in sandbox.

  ``checker_mem_limit``,  ``checker_time_limit``, ``checker_out_limit``
    Just like for executing program, but for checker. Only difference is default
    memory limit raised to 256MiB

Parameters added to the environment:

  ``result_code``
    A short code describing the result: ``OK``, ``OLE`` (Output Limit
    Exceeded), ``RV`` (Rule Violation), ``MLE`` (Memory Limit Exceeded),
    ``TLE`` (Time Limit Exceeded).

  ``result_string``
    A slightly more elaborate description of the status. Only present
    if available. The string may come either from the supervisor of the
    output checker.

  ``result_percentage``
    What percent of maximum score for test should this solution get on this
    test? This value is returned only if output checking is active. Custom
    output checkers can control this value. The default one returns either 100
    or 0.

  ``time_used``
    CPU time used, in milliseconds (only user time is counted, not system).

  ``mem_used``
    Maximum amount of virtual memory used, in kB. Lower-bound estimate.

  ``num_syscalls``
    Number of system calls performed.


.. _output-checker:

Custom output checker
---------------------

The output checker can be any binary program. It is recommended to compile
it statically in 32-bit mode. This program is run by SIO Workers in the
following way::

  # ./checker in_file out_file hint_file

The exit code of the checker is ignored. It should output up to three lines
in the following format::

  OK or WRONG
  [one-line comment]
  [float value --- percentage of full score, only if OK]

for example::

  OK

or::

  WRONG
  not enough edges, expected 15, read 25

or::

  OK
  program scored 40 points, max. was 50
  80

Anything different than ``OK`` in the first line (including nothing) is
treated as ``WRONG``.

Builtin jobs
------------

+--------------+------+------------+-----------------------------------------+
|Name          |Secu\ |Prerequi\   |Info                                     |
|              |re    |sites       |                                         |
+==============+======+============+=========================================+
|``unsafe-``\  |No    |None        |This job provides simple resource        |
|``exec``      |      |            |management relying on ``ulimit``.        |
+--------------+------+------------+-----------------------------------------+
|``cpu-exec``  |Yes   |``exec-``\  |Executes programs in a dedicated, secure |
|              |      |``sandbox`` |sandbox. Because time used by real cpu   |
|              |      |            |is returned, no other job will be        |
|              |      |            |executed simultaneously.                 |
+--------------+------+------------+-----------------------------------------+
|``vcpu-exec`` |Yes   |``vcpu_``\  |This is machine-independent execution    |
|              |      |``exec-``\  |job, which uses instruction counting     |
|              |      |``sandbox`` |for meansuring "runtime" of programs.    |
|              |      |            |It uses a secure sandbox as well.        |
|              |      |            |It uses OiTimeTool.                      |
+--------------+------+------------+-----------------------------------------+
|``sio2jail``\ |Yes   |``sio2``\   |This is machine-independent execution    |
|``-exec``     |      |``jail_``\  |job, which uses instruction counting     |
|              |      |``exec-``\  |for meansuring "runtime" of programs.    |
|              |      |``sandbox`` |It uses a secure sandbox as well.        |
|              |      |            |It uses Sio2Jail.                        |
+--------------+------+------------+-----------------------------------------+


Shell scripts
-------------

The package provides a convenience shell script ``sio-compile`` which
mimicks SIO1's ``compile.sh`` script. It expects three arguments: input file
name, output file name and programming language source file extension
(optionally).


Defining new executors
----------------------

#. (Optional) Create new executing environment: :ref:`executors_env`

#. Copy-and-paste code from ``sio/workers/common.py``, adjust accordingly.

#. Add to ``entry_points`` in ``setup.py``.
