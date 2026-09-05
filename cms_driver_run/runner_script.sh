#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
EOS_OUTPUT_BASE="/eos/uscms/store/group/lpcjm/${USER}/cms_nanoaod"

cd "$SCRIPT_DIR"

mkdir -p "$EOS_OUTPUT_BASE/mc" "$EOS_OUTPUT_BASE/data" logs
chmod +x run_cmsdriver_mc.sh run_cmsdriver_data.sh

if [[ -z "${X509_USER_PROXY:-}" ]]; then
	echo "Warning: X509_USER_PROXY is not set; Condor may not access CMS storage." >&2
fi

condor_submit cms_nanoAODv15_mc.jdl
condor_submit cms_nanoAODv15_data.jdl

condor_q

ls -l "$EOS_OUTPUT_BASE/mc/"
ls -l "$EOS_OUTPUT_BASE/data/"
