#!/usr/bin/env python3
"""Apply the SWEET bring-up changes to an iOS root made by tools/mkiosroot.sh.

  sudo sweet-root-tweaks.py MOUNTED_ROOT

MOUNTED_ROOT is the HFS+ image mounted read-write (Linux: run
`fsck.hfsplus -fy` on the image, then `mount -t hfsplus -o loop,force`).
Run as root (it writes root/mobile owned files). Idempotent. This is what
turned the plain mkiosroot.sh output into the images that reach the home
screen (image versions v8-v14 in NOTES.md):

  launchd.plist   _PanicOnCrash -> _PanicOnCrasX (a crashing daemon must not
                  panic the system); CommCenter jobs removed (no baseband: it
                  crash-loops and Setup blocks on its CoreTelephony XPC)
  containers      /private/var/containers/{Bundle,Data/System,Shared/SystemGroup,Temp}
                  (on iOS they live on the data volume)
  migration       LastSystemVersion so DataMigration does not run for an hour
                  on every boot
  audio           VirtualAudio HAL plug-in disabled (mediaserverd crash)
  os_features     DeviceManagementClient.HRN os_feature flag enabled so lsd's
                  +[LSHRNSupport deviceConfiguredForHRN] short-circuits instead
                  of doing a synchronous activation-record XPC to
                  mobileactivationd (that XPC is the lsd three-way deadlock)
  MediaToolbox    StartRecorderServer=false (camera filter prewarm calls a
                  NULL OpenGL function without a GPU -> mediaserverd crash loop)
  SpringBoard     BKNoWatchdogs (one slow CPU path, no scene-create watchdog
                  kills), no cloud-configuration UI
  Setup           skipped: SetupDone, SetupFinishedAllSteps, SetupVersion 11,
                  mini-buddy flags off
  activation      mobileactivationd data ark seeded; the actual Activated state
                  comes from its Hactivation branch, selected by the /chosen
                  security-status properties in tools/mkadt.py. The container is
                  seeded at BOTH the legacy UUID and the runtime UUID
                  containermanagerd resolves (7D5F4CDD-...), because the daemon
                  traps at brk #0x1 if setResourceValue:NSURLIsExcludedFromBackupKey
                  fails on the missing runtime container path.
"""
import glob, os, plistlib, shutil, sys

BUILD, VERSION = '20H392', '16.7.16'
MOBILE = 501


def load(path):
    with open(path, 'rb') as f:
        return plistlib.load(f)


def save(path, data, uid, gid, mode, fmt=plistlib.FMT_BINARY):
    with open(path, 'wb') as f:
        plistlib.dump(data, f, fmt=fmt)
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def merge_pref(root, name, values):
    """Merge keys into /var/mobile/Library/Preferences/NAME.plist (mobile, 0600)."""
    path = os.path.join(root, 'private/var/mobile/Library/Preferences', name + '.plist')
    data = load(path) if os.path.exists(path) else {}
    data.update(values)
    save(path, data, MOBILE, MOBILE, 0o600)
    print('pref', name, sorted(values))


def launchd(root):
    path = os.path.join(root, 'System/Library/xpc/launchd.plist')
    st = os.stat(path)
    plist = load(path)
    jobs = plist['LaunchDaemons']
    renamed = 0
    for job in jobs.values():
        if '_PanicOnCrash' in job:
            job['_PanicOnCrasX'] = job.pop('_PanicOnCrash')
            renamed += 1
    removed = [k for k, j in jobs.items() if j.get('Label') == 'com.apple.CommCenter']
    for k in removed:
        del jobs[k]
    save(path, plist, st.st_uid, st.st_gid, st.st_mode & 0o7777)
    print(f'launchd.plist: {renamed} _PanicOnCrash renamed, {len(removed)} CommCenter jobs removed')


def containers(root):
    base = os.path.join(root, 'private/var/containers')
    for sub, uid in (('Bundle', 33), ('Data/System', 0), ('Shared/SystemGroup', 0), ('Temp', 0)):
        d = os.path.join(base, sub)
        if not os.path.isdir(d):
            os.makedirs(d)
            os.chown(d, uid, uid)
            os.chmod(d, 0o755)
            print('mkdir', d)


def find_container(root, kind, identifier):
    for meta in glob.glob(os.path.join(root, 'private/var/containers', kind, '*',
                                       '.com.apple.mobile_container_manager.metadata.plist')):
        if load(meta).get('MCMMetadataIdentifier') == identifier:
            return os.path.dirname(meta)
    return None


# UUID of the com.apple.mobileactivationd system container. On iOS this lives
# on the data volume and is created by containermanagerd; our image is a single
# volume with no /private/var/containers at all (mkiosroot.sh only copies the
# OS root), so the container has to be seeded here.
#
# containermanagerd resolves the container to a UUID derived from the
# identifier (a keyed hash, not reproducible offline). On davinci that runtime
# UUID is 7D5F4CDD-1529-4133-9E26-8E449AFC95B3 and it is IDENTICAL in every
# boot: mobileactivationd then does setResourceValue:NSURLIsExcludedFromBackupKey
# on the container path, that path did not exist (only the old D90C94C4-... was
# seeded), the call failed, it threw and trapped at brk #0x1 -> the daemon
# never answers MadGate getActivationState -> SBLockdownManager
# _setupActivationState blocks SpringBoard's main thread forever (proved by
# ipsw symbolication of the t200 sampler stack, NOTES.md 2026-10-21).
#
# Seed the container at BOTH UUIDs so whichever one containermanagerd computes
# finds an existing, correctly-owned directory. D90C94C4-... is what the working
# sweet image v14 used and is kept so find_container() still locates the ark.
MOBILEACTIVATIOND_UUID = 'D90C94C4-F94E-4FCF-8A28-A93BE3846D8E'
MOBILEACTIVATIOND_RUNTIME_UUID = '7D5F4CDD-1529-4133-9E26-8E449AFC95B3'


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


def activation(root):
    c = find_container(root, 'Data/System', 'com.apple.mobileactivationd')
    if c is None:
        c = make_system_container(root, MOBILEACTIVATIOND_UUID, 'com.apple.mobileactivationd')
    # Also seed the UUID containermanagerd resolves at runtime: the daemon does
    # setResourceValue:NSURLIsExcludedFromBackupKey on THAT path and traps when
    # it is missing (see MOBILEACTIVATIOND_RUNTIME_UUID above).
    if find_container(root, 'Data/System', MOBILEACTIVATIOND_RUNTIME_UUID) is None:
        make_system_container(root, MOBILEACTIVATIOND_RUNTIME_UUID,
                              'com.apple.mobileactivationd')
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
        print('data ark', d)


def os_features(root):
    """Enable the DeviceManagementClient.HRN os_feature flag.

    LaunchServices' +[LSHRNSupport deviceConfiguredForHRN] asks
    os_feature_enabled_impl("DeviceManagementClient", "HRN"). When that is
    FALSE it falls through to MAECopyActivationRecordWithError, a synchronous
    XPC to mobileactivationd. On this boot lsd services an
    identifierForVendor/__LSCopyServerStore XPC FROM a process whose
    LaunchServices query can only complete once lsd answers it, so lsd waits on
    mobileactivationd, which waits on lsd: a three-way deadlock (lsd t0 -> lsd
    t5 -> mobileactivationd -> lsd t0, NOTES.md 2026-10-21). With HRN enabled
    deviceConfiguredForHRN returns true at 0x181c2597c and lsd computes the
    vendor identifier locally, with no XPC. HRN is absent from the stock domain
    plist, so os_feature_enabled defaults it to false.
    """
    path = os.path.join(root, 'System/Library/FeatureFlags/Domain',
                        'DeviceManagementClient.plist')
    st = os.stat(path)
    data = load(path)
    data.setdefault('HRN', {}).update(
        {'Enabled': True, 'DevelopmentPhase': 'FeatureComplete'})
    save(path, data, st.st_uid, st.st_gid, st.st_mode & 0o7777, plistlib.FMT_XML)
    print('os_feature DeviceManagementClient.HRN enabled')
    # Belt and braces: the same flag in the Global layer, which
    # init_featureflags also folds into com.apple.featureflags.shm.
    gpath = os.path.join(root, 'System/Library/FeatureFlags/Global.plist')
    st = os.stat(gpath)
    g = load(gpath)
    g.setdefault('DeviceManagementClient', {}).setdefault('HRN', {}).update(
        {'Enabled': True, 'DevelopmentPhase': 'FeatureComplete'})
    save(gpath, g, st.st_uid, st.st_gid, st.st_mode & 0o7777, plistlib.FMT_XML)
    print('os_feature Global DeviceManagementClient.HRN enabled')


def audio(root):
    src = os.path.join(root, 'Library/Audio/Plug-Ins/HAL/VirtualAudio.plugin')
    dst_dir = os.path.join(root, 'Library/Audio/Plug-Ins/HAL.disabled')
    if os.path.exists(src):
        os.makedirs(dst_dir, exist_ok=True)
        shutil.move(src, dst_dir)
        print('VirtualAudio.plugin disabled')
    for conf in glob.glob(os.path.join(root, 'System/Library/Frameworks/MediaToolbox.framework/*/SubServerConfiguration.plist')):
        st = os.stat(conf)
        data = load(conf)
        data['StartRecorderServer'] = False
        save(conf, data, st.st_uid, st.st_gid, st.st_mode & 0o7777, plistlib.FMT_XML)
        print('StartRecorderServer off', os.path.relpath(conf, root))


def main():
    if len(sys.argv) != 2 or not os.path.isdir(os.path.join(sys.argv[1], 'System/Library/xpc')):
        sys.exit(__doc__)
    root = sys.argv[1]
    launchd(root)
    containers(root)
    activation(root)
    os_features(root)
    audio(root)
    merge_pref(root, 'com.apple.migration', {
        'LastSystemVersion': BUILD,
        'DMUserDataDisposition': {'SyntheticDidUpgrade': False, 'buildVersion': BUILD}})
    merge_pref(root, 'com.apple.springboard', {
        'BKNoWatchdogs': True,
        'FBLaunchWatchdogExceptions': {'com.apple.purplebuddy': 100.0},
        'MCForceShowCloudConfigurationUI': False})
    merge_pref(root, 'com.apple.purplebuddy', {
        'SetupDone': True, 'SetupFinishedAllSteps': True, 'SetupVersion': 11,
        'daemonizeNeedsToRun': False})
    merge_pref(root, 'com.apple.purplebuddy.notbackedup', {
        k: False for k in ('ShouldRunDiagnosticsMiniBuddy', 'ShouldRunHSA2MiniBuddy',
                           'ShouldRunKeychainSyncMiniBuddy', 'ShouldRunMesaMiniBuddy',
                           'ShouldRunPaymentMiniBuddy', 'ShouldRunStandardMiniBuddy',
                           'SilentICDPUpgrade')})
    merge_pref(root, 'com.apple.managedconfiguration.notbackedup', {
        'LockdownActivationIndicatesCloudConfigurationAvailable': False})


if __name__ == '__main__':
    main()
