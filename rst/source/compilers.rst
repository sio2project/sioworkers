Compilers
=========

This package provides one SIO Workers job, namely ``compile``.

``compile``, given a source file, detects its language, compiles
it and saves the binary file. All I/O is made via the filetracker.

Each programming language is represented
by a *language code*. Built-in language codes are ``c``, ``cpp``,
``pas``.

Job parameters
--------------

The following parameters are recognized in ``environ``:

  ``source_file``
    Filetracker path of the program to compile.

  ``out_file``
    Filetracker path where the compiled file will be saved. Mandatory.

  ``compiler``
    (optional) Name of compiler to use.

    If not specified, the name ``default-<ext>`` is used, where ``<ext>`` is the
    extension of the ``source_file``, all lowercase.

  ``compilation_mem_limit``, ``compilation_time_limit``, ``compilation_real_time_limit``
    (optional) Resource limits for the compiler process, passed to
    relevant :ref:`executor <executors_env>`.

  ``compilation_output_limit``
    (optional) Limits length of compiler output returned to user when
    compilation error occurs. By default set to 5KiB, set to None for unlimited.
    Passed to relevant :ref:`executor <executors_env>`.

  ``compilation_result_size_limit``
    (optional) Limit for size of the compiled file.

  ``additional_includes``
    This option allows additional files, such as header files, to be seen during
    compilation. This parameters can take one of the following forms:

        * ``string`` - Filetracker path to the file. It will be placed in
          the same directory as the source file.
        * ``tuple`` or ``list`` - Iterable of filetracker paths.
        * ``dict`` - if given a dictionary, ``sio.compilers`` will select
          a key equal to the language code of the source file.
          The value will can be either a string or an iterable.

  ``additional_sources``
    Allows additional source files to be compiled and linked with the
    ``source_file``. This option is analogous to ``additional_includes``

  ``additional_archive``
    An archive in Zip format to be extracted in the compilation directory.
    Individual files are not extracted in case they would overwrite existing
    ones (e.g. ``additional_includes``) or if they would end up outside of
    the compilation directory (when their path starts with ``..``).

  ``extra_files``
    This option allows additional files to be available, in the same directory,
    during compilation. It should be a ``dict`` with
    keys representing intended filenames and values -- paths in the filetracker.

Parameters added to the environment:

  ``compiler_output``
    Stdout + stderr from the compiler (frequently an empty string).

  ``result_code``
    ``OK`` or ``CE`` (Compilation Error).

Available compilers
-------------------

The package provides two kinds of compilers: sandboxed and non-sandboxed.

Sandboxed compilers run their compilation process inside a curated compiler,
with hand-picked libraries carefully selected by an experienced team
of security experts. See `sio.workers.sandbox` for more.

Each sandboxed compiler requires a download of packages a few hundreds
of megabytes large, it may be therefore preferable to just run a default
compiler available on the system.

Built-in sandboxed compilers:

* ``c`` (aliases: ``gcc``, ``default-c``)
* ``cpp`` (aliases: ``g++``, ``default-cc``, ``default-cpp``)
* ``pas`` (aliases: ``fpc``, ``default-pas``)

Built-in non-sandboxed compilers:

* ``system-c`` (aliases: ``system-gcc``)
* ``system-cpp`` (aliases: ``system-g++``)
* ``system-pas`` (aliases: ``system-fpc``)

.. note::
    Testing sandboxed compilers is disabled by default. To enable it,
    run ``nosetests`` with environment variable ``TEST_SANDBOXES`` set to ``1``.

Shell scripts
-------------

The package provides a convenience shell script ``sio-compile`` which
mimicks SIO1's ``compile.sh`` script. It expects three arguments: input file
name, output file name and programming language source file extension
(optionally).


Defining new compilers
----------------------

#. Copy-and-paste code from ``sio/compilers/template.py``, adjust accordingly
   (check out existing compilers for inspiration).

#. Add to ``entry_points`` in ``setup.py``.

