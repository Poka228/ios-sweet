#!/usr/bin/env python3
"""Seed the mobileactivationd system container(s) into an iOS root.

  sudo sweet-seed-container.py MOUNTED_ROOT

Why: mobileactivationd calls `setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey`
on the container path containermanagerd hands it and traps (`brk #0x1`,
EXC_BREAKPOINT at main+0x1BF504) when that path does not exist.  The crash shows up
in the SWEET console ring as

  CRASH mobileactivation sig 5 code 0x600000001 ... pc == lr
  reason ns 2 code 0x5: (none)

and SpringBoard then blocks forever in `-[SBLockdownManager _setupActivationState]`
-> `MadGate getActivationState:` (synchronous XPC to the dead daemon) -- no lock
screen.  Seeding the container at BOTH the legacy UUID and the UUID
containermanagerd actually resolves (captured from a boot of this image) removes the
trap; tools/sweet-root-tweaks.py then writes the data ark into it.

Run it BEFORE tools/sweet-root-tweaks.py (that script only warns if the container is
missing).  The reference image from Antcating/ios-davinci has no containers at all,
so this is our deviation; it is data-only (no signed binaries are touched).
"""
import os
import plistlib
import sys

BUILD, VERSION = '20H392', '16.7.16'
MOBILE = 501

MOBILEACTIVATIOND_UUID = 'D90C94C4-F94E-4FCF-8A28-A93BE3846D8E'
MOBILEACTIVATIOND_RUNTIME_UUID = '7D5F4CDD-1529-4133-9E26-8E449AFC95B3'


def save(path, data, uid, gid, mode, fmt=plistlib.FMT_BINARY):
    with open(path, 'wb') as f:
        plistlib.dump(data, f, fmt=fmt)
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def find_container(root, kind, identifier):
    import glob
    for meta in glob.glob(os.path.join(root, 'private/var/containers', kind, '*',
                                       '.com.apple.mobile_container_manager.metadata.plist')):
        with open(meta, 'rb') as f:
            if plistlib.load(f).get('MCMMetadataIdentifier') == identifier:
                return os.path.dirname(meta)
    return None


def make_system_container(root, uuid, identifier):
    """Create a Data/System container with the metadata containermanagerd reads."""
    c = os.path.join(root, 'private/var/containers/Data/System', uuid)
    os.makedirs(c, exist_ok=True)
    os.chown(c, 0, 0)
    os.chmod(c, 0o755)
    save(os.path.join(c, '.com.apple.mobile_container_manager.metadata.plist'), {
        'MCMMetadataIdentifier': identifier,
        'MCMMetadataUUID': uuid,
        'MCMMetadataContentClass': 1,
        'MCMMetadataMinOSVersion': '16.0',
        'MCMMetadataInfoMinOSVersion': '16.0',
        'MCMMetadataDataSeparatedShareUUID': uuid,
        'MCMMetadataUserIdentity': '0:0:0:0:0:0:0:0:0:0:0:0:0:0:0:0',
        'MCMMetadataIsDataSeparated': False,
    }, 0, 0, 0o644)
    print('system container', identifier, uuid)
    return c


def main():
    root = sys.argv[1]
    for uuid in (MOBILEACTIVATIOND_UUID, MOBILEACTIVATIOND_RUNTIME_UUID):
        make_system_container(root, uuid, 'com.apple.mobileactivationd')
    ark = {
        '-ActivationState': 'Activated', '-BrickState': False,
        '-BuildVersion': BUILD, '-ProductVersion': VERSION,
        '-DataMigrationCompleted': True, '-PreSydroDataMigrationCompleted': True,
    }
    for uuid in (MOBILEACTIVATIOND_UUID, MOBILEACTIVATIOND_RUNTIME_UUID):
        d = os.path.join(root, 'private/var/containers/Data/System', uuid, 'Library/internal')
        os.makedirs(d, exist_ok=True)
        os.chown(d, MOBILE, MOBILE)
        os.chmod(d, 0o755)
        save(os.path.join(d, 'data_ark.plist'), ark, MOBILE, MOBILE, 0o600)
        print('data ark', os.path.relpath(d, root))


if __name__ == '__main__':
    main()
