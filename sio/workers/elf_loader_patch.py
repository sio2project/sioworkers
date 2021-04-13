from __future__ import absolute_import
import os, os.path
import logging

logger = logging.getLogger(__name__)

EXT = '.old_elf_loader'


def _get_unpatched_name(path):
    return '%s%s' % (path, EXT)


def _patch_elf_loader(path):
    """Patches ELF files making them use loader from sandbox.

    Modifies all executable ELF files in the sandbox so that they are run
    with the standard library included in the sandbox, including its ld.so.
    Unfortunately we had a need to run our sandboxes in an old environment
    with even too old ld.so to run the newest binaries.

    This is done by renaming the original executables and putting simple
    shell scripts in place.

    All ELF files which are not .so, .so.*, .o or are listed in
    ``<sandbox_root>/.elf_patcher_blacklist`` and which have the
    executable bit set are processed.

    In ``<sandbox_root>/.elf_patcher_blacklist`` you can list
    (new line separated) files and directories which should be ignored by
    _patch_elf_loader.
    """

    path = os.path.abspath(path)
    loader = os.path.join(path, 'lib', 'ld-linux.so.2')
    if not os.path.exists(loader):
        logger.info("Not patching sandbox: %s", path)
        return False
    rpath = '%s:%s' % (os.path.join(path, 'lib'), os.path.join(path, 'usr', 'lib'))

    blacklist_file = os.path.join(path, '.elf_patcher_blacklist')
    blacklist = set()
    if os.path.exists(blacklist_file):
        blacklist = set(
            [
                os.path.join(path, f.strip(os.path.sep))
                for f in open(blacklist_file, 'rb').read().strip().split('\n')
            ]
        )

    logger.info("Patching sandbox: %s", path)
    logger.info("Patcher blacklist: %s", blacklist)
    for root, dirs, files in os.walk(path):
        if root in blacklist:
            # Prune the search down this directory
            del dirs[:]
            continue

        for file in files:
            p = os.path.join(root, file)
            pext = _get_unpatched_name(p)

            if (
                p in blacklist
                or not os.access(p, os.X_OK)
                or os.path.islink(p)
                or file.endswith(EXT)
                or os.path.exists(pext)
                or file.endswith('.so')
                or '.so.' in file
                or file.endswith('.o')
            ):
                continue

            with open(p, 'rb') as f:
                if f.read(4) != '\x7fELF':
                    continue
            logger.info("Patching ELF loader of %s", p)
            os.rename(p, pext)

            with open(p, 'w') as f:
                f.write(
                    '#!/bin/sh\n'
                    'exec %(loader)s --library-path %(rpath)s '
                    '--inhibit-rpath %(original)s %(original)s "$@"\n'
                    % {'loader': loader, 'original': pext, 'rpath': rpath}
                )
                mode = os.stat(pext).st_mode
                os.fchmod(f.fileno(), mode)

    return True
