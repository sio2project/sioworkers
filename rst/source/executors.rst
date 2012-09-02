Executors
=========

This package provides one SIO Workers job, named ``exec``, which can be used
to run arbitrary binary programs under a supervisor program in a secure way.

This job also allows to check the correctness of the output produced by the
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

  ``exec_et_limit``
    Exectime limit (i.e. the limit of number of CPU instructions executed).

    Default: 0 (no limit)

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

  ``exectime_used``
    Exectime user, i.e. the number of CPU instructions executed. May be an
    invalid value if appropriate kernel modules are not available.

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

Simple (unsafe) implementation
------------------------------

There is also another job type provided by this module -- it's ``unsafe-exec``.
It doesn't use the supervisor, but instead relies on simple ulimit resource
limiting. It does not need a sandbox.

Instruction counting
--------------------

Another, machine-independent execution job, is called ``vcpu-exec``. It uses
instruction counting for measuring "runtime" of programs.

Prerequisites
-------------

This may sound obvious, but the job requires that appropriate sandboxes named
(``exec-sandbox``, ``vcpu_exec-sandbox``) are available.


Shell scripts
-------------

The package provides a convenience shell script ``sio-compile`` which
mimicks SIO1's ``compile.sh`` script. It expects three arguments: input file
name, output file name and programming language source file extension
(optionally).


Defining new compilers
----------------------

#. Copy-and-paste code from ``sio/compilers/template.py``, adjust accordingly.

#. Add to ``entry_points`` in ``setup.py``.

