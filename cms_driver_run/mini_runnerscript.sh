#!/bin/bash

# 0. Create EOS output directories
#mkdir -p /eos/uscms/store/user/${USER}/cms_nanoaod/mc
#mkdir -p /eos/uscms/store/user/${USER}/cms_nanoaod/data

cd "$(dirname "$0")"

# 1. Add user proxy for xrootd to be used in batch
export X509_USER_PROXY=$X509_USER_PROXY

# 2. Submit Data job
#condor_submit cms_nanoAODv15_data.jdl

# 2. Submit MC job
condor_submit cms_nanoAODv15_mc.jdl

# 3. Monitor jobs
condor_q


# 4. Check EOS output
ls -l /eos/uscms/store/user/${USER}/cms_nanoaod/mc/
ls -l /eos/uscms/store/user/${USER}/cms_nanoaod/data/
