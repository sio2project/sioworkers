
import os.path
from sio.workers import ft, Failure
from sio.workers.executors import UnprotectedExecutor, PRootExecutor

DEFAULT_COMPILER_TIME_LIMIT = 30000  # in ms
DEFAULT_COMPILER_MEM_LIMIT = 256 << 10  # in kbytes
DEFAULT_COMPILER_OUTPUT_LIMIT = 5 << 10  # in bytes

def _lang_option(environ, key, lang):
    value = environ.get(key, ())
    if isinstance(value, dict):
        value = value.get(lang, ())
    if isinstance(value, basestring):
        value = (value,)
    return value

def run(environ, lang, compiler, extension, output_file, compiler_options=(),
        compile_additional_sources=True, sandbox=False,
        sandbox_callback=None):
    """
    Common code for compiler handlers:

    :param environ: Recipe to pass to `filetracker` and `sio.workers.execute`
                    For all supported options, see the global documentation for
                    `sio.compilers`.
    :param lang: Language code (for example: `c`, `cpp`, `pas`)
    :param compiler: Compiler binary name
    :param extension: Usual extension for source files of the given language.
    :param output_file: Default output binary file, assuming the input is named
                        `a.<extension>`
    :param compiler_options: Optional tuple of command line parameters to the
                             compiler.
    :param compile_additional_sources: Enables passing additional
                                       source files to the compiler - used
                                       as a hack to support FPC.
                                       Defaults to True.
    :param sandbox: Enables sandboxing (using compiler name
                    as a sandbox). Defaults to False.
    :param sandbox_callback: Optional callback called immediately after
                             creating the executor, with the said executor
                             and the command argument list as arguments.
                             Should return new command if modified.
    """

    if sandbox is False:
        executor = UnprotectedExecutor()
    else:
        executor = PRootExecutor('compiler-' + environ['compiler'])

    extra_compilation_args = \
            _lang_option(environ, 'extra_compilation_args', lang)

    ft.download(environ, 'source_file', 'a.' + extension)
    cmdline = [compiler, ] + list(compiler_options) + \
                list(extra_compilation_args) + ['a.' + extension, ]
    # this cmdline may be later extended

    # using a copy of the environment in order to avoid polluting it with
    # temoporary elements
    tmp_environ = environ.copy()

    additional_includes = _lang_option(environ, 'additional_includes', lang)
    additional_sources = _lang_option(environ, 'additional_sources', lang)

    for include in additional_includes:
        tmp_environ['additional_include'] = include
        ft.download(tmp_environ, 'additional_include',
                    os.path.basename(include))

    for source in additional_sources:
        tmp_environ['additional_source'] = source
        ft.download(tmp_environ, 'additional_source',
                    os.path.basename(source))
        if compile_additional_sources:
            cmdline += [os.path.basename(source), ]

    extra_files = environ.get('extra_files', {})
    for name, ft_path in extra_files.iteritems():
        tmp_environ['extra_file'] = ft_path
        ft.download(tmp_environ, 'extra_file', os.path.basename(name))

    with executor:
        if sandbox_callback:
            cmdline = sandbox_callback(executor, cmdline) or cmdline

        renv = executor(cmdline,
                                  time_limit=DEFAULT_COMPILER_TIME_LIMIT,
                                  mem_limit=DEFAULT_COMPILER_MEM_LIMIT,
                                  output_limit=DEFAULT_COMPILER_OUTPUT_LIMIT,
                                  ignore_errors=True,
                                  environ=tmp_environ,
                                  environ_prefix='compilation_',
                                  capture_output=True,
                                  forward_stderr=True)

    environ['compiler_output'] = renv['stdout']
    if renv['return_code']:
        environ['result_code'] = 'CE'
    elif 'compilation_result_size_limit' in environ and \
            os.path.getsize(output_file) > \
            environ['compilation_result_size_limit']:
        environ['result_code'] = 'CE'
        environ['compiler_output'] = 'Compiled file size limit exceeded.'
    else:
        environ['result_code'] = 'OK'
        ft.upload(environ, 'out_file', output_file)

    return environ

