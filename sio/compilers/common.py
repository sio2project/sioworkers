# pylint: disable=attribute-defined-outside-init
from __future__ import absolute_import
import os.path
import logging
from zipfile import ZipFile

from sio.workers import ft
from sio.workers.executors import UnprotectedExecutor, PRootExecutor
from sio.workers.util import replace_invalid_UTF, tempcwd
import six

logger = logging.getLogger(__name__)

DEFAULT_COMPILER_TIME_LIMIT = 30000  # in ms
DEFAULT_COMPILER_MEM_LIMIT = 512 * 2**10  # in KiB
DEFAULT_COMPILER_OUTPUT_LIMIT = 5 * 2**10  # in KiB


def _lang_option(environ, key, lang):
    value = environ.get(key, ())
    if isinstance(value, dict):
        value = value.get(lang, ())
    if isinstance(value, six.string_types):
        value = (value,)
    return value


def _extract_all(archive_path):
    target_path = tempcwd()
    with ZipFile(tempcwd(archive_path), 'r') as zipf:
        for name in zipf.namelist():
            filename = name.rstrip('/')
            extract_path = os.path.join(target_path, filename)
            extract_path = os.path.normpath(os.path.realpath(extract_path))
            if os.path.exists(extract_path):
                logger.warning("Cannot extract %s, file already exists.",
                        extract_path)
            elif not extract_path.startswith(target_path):
                logger.warning("Cannot extract %s, target path outside "
                        "working directory.", extract_path)
            else:
                zipf.extract(name, target_path)


class Compiler(object):
    """
    Base class for implementing compilers. Override some fields and methods
    in a subclass to match your needs.
    """
    sandbox = None
    #: Language code (for example: `c`, `cpp`, `pas`)
    lang = ''
    #: Default output binary file.
    output_file = ''

    def __init__(self, sandbox=None):
        """
        :param sandbox: If specified, commands will be executed in an isolated
                        environment with the sandbox as root directory.
        """
        if sandbox is not None:
            self.sandbox = sandbox

        if self.sandbox is None:
            self.executor = UnprotectedExecutor()
        else:
            self.executor = PRootExecutor('compiler-' + self.sandbox)

    def compile(self, environ):
        """
        Compile the file specified in the `environ` dictionary.

        :param environ: Recipe to pass to `filetracker` and
                    `sio.workers.execute` For all supported options,
                    see the global documentation for `sio.compilers`.
        """
        self.environ = environ
        # using a copy of the environment in order to avoid polluting it with
        # temoporary elements
        self.tmp_environ = environ.copy()

        self.source_file = self._make_filename()
        ft.download(environ, 'source_file', self.source_file)

        self._process_extra_files()
        self.extra_compilation_args = \
                _lang_option(environ, 'extra_compilation_args', self.lang)

        with self.executor as executor:
            renv = self._run_in_executor(executor)

        return self._postprocess(renv)

    def _make_filename(self):
        return 'a.' + self.lang

    def _process_extra_files(self):
        self.additional_includes = _lang_option(self.environ,
                                                'additional_includes',
                                                self.lang)
        self.additional_sources = _lang_option(self.environ,
                                               'additional_sources', self.lang)

        for include in self.additional_includes:
            self.tmp_environ['additional_include'] = include
            ft.download(self.tmp_environ, 'additional_include',
                        os.path.basename(include))

        for source in self.additional_sources:
            self.tmp_environ['additional_source'] = source
            ft.download(self.tmp_environ, 'additional_source',
                        os.path.basename(source))

        extra_files = self.environ.get('extra_files', {})
        for name, ft_path in six.iteritems(extra_files):
            self.tmp_environ['extra_file'] = ft_path
            ft.download(self.tmp_environ, 'extra_file', os.path.basename(name))

        archive = self.environ.get('additional_archive', '')
        if archive:
            self.tmp_environ['additional_archive'] = archive
            archive_path = os.path.basename(archive)
            ft.download(self.tmp_environ, 'additional_archive', archive_path)
            _extract_all(archive_path)

    def _make_cmdline(self, executor):
        raise NotImplementedError

    def _run_in_executor(self, executor):
        cmdline = self._make_cmdline(executor)

        return self._execute(executor, cmdline)

    def _execute(self, executor, cmdline, **kwargs):
        defaults = dict(
                time_limit=DEFAULT_COMPILER_TIME_LIMIT,
                mem_limit=DEFAULT_COMPILER_MEM_LIMIT,
                output_limit=DEFAULT_COMPILER_OUTPUT_LIMIT,
                ignore_errors=True,
                environ=self.tmp_environ,
                environ_prefix='compilation_',
                capture_output=True,
                forward_stderr=True)
        defaults.update(kwargs)
        return executor(cmdline, **defaults)

    def _postprocess(self, renv):
        self.environ['compiler_output'] = replace_invalid_UTF(renv['stdout'])
        if renv['return_code']:
            self.environ['result_code'] = 'CE'
        elif 'compilation_result_size_limit' in self.environ and \
                os.path.getsize(tempcwd(self.output_file)) > \
                self.environ['compilation_result_size_limit']:
            self.environ['result_code'] = 'CE'
            self.environ['compiler_output'] = \
                    'Compiled file size limit exceeded.'
        else:
            self.environ['result_code'] = 'OK'
            self.environ['exec_info'] = {'mode': 'executable'}
            ft.upload(self.environ, 'out_file', tempcwd(self.output_file))

        return self.environ
