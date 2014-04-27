from sio.compilers.common import Compiler


class FPCCompiler(Compiler):
    lang = 'pas'
    output_file = 'a'

    def _make_cmdline(self, executor):
        # Addinational sources are automatically included
        return ['fpc', 'a.pas'] + list(self.extra_compilation_args)


def run(environ):
    return FPCCompiler().compile(environ)

