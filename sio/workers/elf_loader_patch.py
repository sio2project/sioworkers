from sio.workers.execute import execute
import os, os.path
import logging

logger = logging.getLogger(__name__)

EXT = '.old_elf_loader'

def _patch_elf_loader(path):
    # Modifies all executable ELF files in the sandbox so that they are run
    # with the standard library included in the sandbox, including its ld.so.
    # Unfortunately we had a need to run our sandboxes in an old environment
    # with even too old ld.so to run the newest binaries.
    #
    # This is done by renaming the original executables and putting simple
    # shell scripts in place.
    #
    # All ELF files which are not .so, .so.* or .o and which have the
    # executable bit set are processed.

    path = os.path.abspath(path)
    loader = os.path.join(path, 'lib', 'ld-linux.so.2')
    if not os.path.exists(loader):
        return
    rpath = '%s:%s' % (os.path.join(path, 'lib'),
            os.path.join(path, 'usr', 'lib'))
    for root, dirs, files in os.walk(path):
        for file in files:
            p = os.path.join(root, file)
            pext = p + EXT
            if not os.access(p, os.X_OK):
                continue
            if file.endswith(EXT):
                continue
            if os.path.exists(pext):
                continue
            if file.endswith('.so') or '.so.' in file or file.endswith('.o'):
                continue
            with open(p, 'rb') as f:
                if f.read(4) != '\x7fELF':
                    continue
            logger.info("Patching ELF loader of %s", p)
            os.rename(p, pext)
            with open(p, 'w') as f:
                f.write('#!/bin/sh\n'
                        'exec %(loader)s --library-path %(rpath)s '
                        '--inhibit-rpath %(original)s %(original)s "$@"\n' %
                        {'loader': loader, 'original': pext, 'rpath': rpath})
                mode = os.stat(pext).st_mode
                os.fchmod(f.fileno(), mode)
