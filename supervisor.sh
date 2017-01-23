#!/bin/bash

help() {
cat << EOF
Usage: $0 [option] command
Helps managing supervisor with configuration in this script. The only way to
reload configuration is to restart supervisor with this script.

Options:
  -h, --help    display this help

Commands:
  start         starts supervisor
  stop          stops supervisor
  restart       restart supervisor
  status        shows status of daemons that supervisor run
  shell         run supervisorctl's shell
EOF
}

command=
while [ -n "$1" ]; do
    case "$1" in
        "-h"|"--help")
            help
            exit 0
            ;;
        "start"|"stop"|"restart"|"status"|"shell")
            command="$1"
            ;;
        *)
            echo "Unknown option: $1"
            help
            exit 1
            ;;
    esac
    shift
done

if [ -z "$command" ]; then
    help
    exit 1
fi

# Set CWD to directory with config.
cd $(dirname $BASH_SOURCE)/config

if ! [ -e supervisord.conf ] || \
   ! [ -e supervisord-conf-vars.conf ]; then
    echo "Please make sure that supervisord.conf and " \
         "supervisord-conf-vars.conf exist in config/ directory!"
    echo "You can copy example configs that resides in config/ directory."
    exit 1
fi

# Activate venv:
source ../../venv/bin/activate

# Set all config variables.
source supervisord-conf-vars.conf

# Create necessary directories.
mkdir -pv ${WORKER_HOME}/{logs,pidfiles}

# And run supervisor.*
case "$command" in
    "start")
        supervisord
        ;;
    "stop")
        supervisorctl shutdown
        ;;
    "restart")
        supervisorctl shutdown
        supervisord
        ;;
    "status")
        supervisorctl status
        ;;
    "shell")
        echo "Caution: In order to reload config, run \`$0 restart\`"
        supervisorctl
        ;;
esac

