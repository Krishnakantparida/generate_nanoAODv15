#!/bin/bash

# 1. Verify EOS access
ls /eos/uscms/store/user/${USER}

# 2. Create EOS output directories
mkdir -p /eos/uscms/store/user/${USER}/cms_nanoaod/mc
mkdir -p /eos/uscms/store/user/${USER}/cms_nanoaod/data

# 3. Create all 5 files above (copy-paste the content)

cd "$(dirname "$0")"

# 4. Make scripts executable
chmod +x run_cmsdriver_mc.sh
chmod +x run_cmsdriver_data.sh

# Add user proxy for xrootd to be used in batch
export X509_USER_PROXY=$X509_USER_PROXY

# 5. Submit MC job
condor_submit cms_nanoAODv15_mc.jdl

# 6. Submit Data job
condor_submit cms_nanoAODv15_data.jdl

# 7. Monitor jobs
condor_q

# 8. Check EOS output
ls -l /eos/uscms/store/user/${USER}/cms_nanoaod/mc/
ls -l /eos/uscms/store/user/${USER}/cms_nanoaod/data/
