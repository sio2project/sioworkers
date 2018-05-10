from __future__ import absolute_import
from __future__ import print_function
import os.path
from sio.workers import ft

# This function should be registered in setuptools' entry_points,
# under group 'sio.compilers', with a meaningful name, which will
# be matched from environ['compiler']. Specifically if environ['compiler']
# contains a dot, only the prefix before the dot is matched to find
# a suitable compiler.
#
# Default compiler for file extension 'foo' should also be registered under
# 'default-foo'. Extensions are matched in lowercase. There is no need
# to register default compilers for upper-case extensions.
def run(environ):
    if environ['compiler'] not in ('foo.1_0', 'foo.2_0'):
        raise RuntimeError("Compiler '%s' not found.", environ['compiler'])
    input_file = ft.download(environ, 'source_file', 'a.foo')
    print(input_file)
    size = os.path.getsize(input_file)
    out = open('compiled', 'w')
    out.write("#!/bin/sh\n")
    out.write("# Compiled using Foo compiler named %s\n" % environ['compiler'])
    out.write("echo %d" % size)
    out.close()
    ft.upload(environ, 'out_file', 'compiled')
    return environ

# This function is registered as default compiler for extension '.foo'
def run_default(environ):
    environ['compiler'] = 'foo.1_0'
    return run(environ)
