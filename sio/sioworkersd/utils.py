# Default ram requirements in KiB
# This is in KiB because oioioi apparently mostly uses KiB,
# while sioworkersd uses MiB.
DEFAULT_RAM_REQUIREMENTS = {
   'ping': 1 * 1024,
   'ingen': 256 * 1024,
   'inwer': 256 * 1024,
   'compile': 512 * 1024,
   'exec': 64 * 1024,
   'checker': 268 * 1024,
   'default': 256 * 1024,
}


# Returns ram required for specific job in MiB
def get_required_ram_for_job(env):
    job_type = env['job_type']
    if job_type.endswith('exec'):
        required_ram = env.get('exec_mem_limit',
            DEFAULT_RAM_REQUIREMENTS['exec'])
        # We need to make sure that we have enough ram for a checker as well.
        if env.get('check_output'):
            required_ram = max(required_ram, env.get('checker_mem_limit',
                    DEFAULT_RAM_REQUIREMENTS['checker']))
    else:
        required_ram = env.get(job_type + '_mem_limit',
                DEFAULT_RAM_REQUIREMENTS.get(job_type,
                        DEFAULT_RAM_REQUIREMENTS['default']))

    # Convert KiB to MiB
    return required_ram / 1024
