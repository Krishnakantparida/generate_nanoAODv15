# generate_nanoAODv15

Utilities for producing customized CMS Run 3 NanoAOD v15 and NanoAODSIM files from MiniAOD/MiniAODSIM inputs.

The customization adds AK8 raw two-prong subjet branches to the `FatJet` table. For each `slimmedJetsAK8` jet, the local CMSSW plugin reclusters its constituents with Cambridge-Aachen R=0.8, declusters the leading CA jet until the leading resolved two-prong split is found, and stores the larger-pT prong as `raw_sj1` and the other as `raw_sj2`.

New NanoAOD branches:

- `FatJet_raw_sj1_pt`, `FatJet_raw_sj1_eta`, `FatJet_raw_sj1_phi`, `FatJet_raw_sj1_mass`, `FatJet_raw_sj1_nConstituents`
- `FatJet_raw_sj2_pt`, `FatJet_raw_sj2_eta`, `FatJet_raw_sj2_phi`, `FatJet_raw_sj2_mass`, `FatJet_raw_sj2_nConstituents`

Missing raw subjet values are filled with `-99` for floating-point branches and `0` for constituent counts.

## Repository Layout

- `MyAnalysis/JetTools/`: CMSSW plugin code for AK8 CA R=0.8 reclustering and declustering.
- `cmsskim_customize.py`: cmsDriver customizations for the AK8 raw subjets, GloParT subjet variables, and the single-muon plus fat-jet skim.
- `miniAOD+SIM_sample_query/`: YAML files containing DAS dataset queries.
- `cms_driver_run/`: HTCondor-oriented cmsDriver/cmsRun scripts and JDL files.
- `crab_run/`: CRAB job preparation and submission helper.

## Clone on CMSLPC or lxplus

Clone the repository in a work area with enough quota for a CMSSW release and batch-generated configs. On CMSLPC, a `nobackup` area is usually a good choice:

```bash
cd /uscms/home/$USER/nobackup
git clone https://github.com/Krishnakantparida/generate_nanoAODv15.git
cd generate_nanoAODv15
```

On lxplus, use an EOS or work area where you can create CMSSW releases and CRAB projects:

```bash
cd /eos/user/${USER:0:1}/$USER
git clone https://github.com/Krishnakantparida/generate_nanoAODv15.git
cd generate_nanoAODv15
```

Required tools and access:

- `/cvmfs/cms.cern.ch` mounted and readable.
- `git`, `python3`, `scramv1`, `cmsDriver.py`, and `cmsRun`.
- `dasgoclient` for YAML-driven file discovery.
- `condor_submit` for CMSLPC HTCondor running, or `crab` for CRAB submission.
- A valid CMS proxy, created with `voms-proxy-init -rfc -voms cms -valid 192:00`.
- Write access to `/eos/uscms/store/group/lpcjm/$USER/` for the default output location.

## CMSSW Setup

Use the same release and architecture as the runner scripts:

```bash
source /cvmfs/cms.cern.ch/cmsset_default.sh
export SCRAM_ARCH=el9_amd64_gcc12
scramv1 project CMSSW CMSSW_15_0_15_patch4
cd CMSSW_15_0_15_patch4/src
eval "$(scramv1 runtime -sh)"
```

For local builds, copy or symlink this repository's `MyAnalysis` package into `CMSSW_BASE/src` and build it:

```bash
cp -R /path/to/generate_nanoAODv15/MyAnalysis "$CMSSW_BASE/src/"
scram b -j8
```

The Condor scripts also transfer and build `MyAnalysis` automatically inside the batch job sandbox.

## Running With HTCondor

Prepare chunk files in `cms_driver_run/` directly from the YAML headers:

```bash
cd cms_driver_run
python3 prepare_condor_chunks.py ../miniAOD+SIM_sample_query/muon_2024_miniAOD_DATA.yaml --mode data --files-per-chunk 5
python3 prepare_condor_chunks.py ../miniAOD+SIM_sample_query/muon_2024_miniAODSIM_MC.yaml --mode mc --files-per-chunk 5
```

This writes header-aware chunk files for the Condor JDLs in `cms_driver_run/`.

You can also prepare chunk files manually in `cms_driver_run/`:

- data chunks: `miniAOD_chunk_0.txt`, `miniAOD_chunk_1.txt`, ...
- MC chunks: `miniAODSIM_chunk_0.txt`, `miniAODSIM_chunk_1.txt`, ...
- header-aware data chunks: `miniAOD_chunk_singlemu0_0.txt`, ...
- header-aware MC chunks: `miniAODSIM_chunk_ttbar-powheg_0.txt`, ...

Each line should be a MiniAOD/MiniAODSIM logical file name, for example `/store/.../file.root`.

Then submit both data and MC jobs with the single runner script:

```bash
cd cms_driver_run
./runner_script.sh
```

The runner creates the EOS output directories and Condor log directory,
ensures the job scripts are executable, submits both JDLs, displays the queue,
and lists the data and MC output locations.

Outputs are copied to:

- data: `/eos/uscms/store/group/lpcjm/$USER/cms_nanoaod/data/<yaml-header>/`
- MC: `/eos/uscms/store/group/lpcjm/$USER/cms_nanoaod/mc/<yaml-header>/`

The JDL files transfer `../cmsskim_customize.py`, `../MyAnalysis`, and the chunk file from `cms_driver_run`, so the submission directory is relocatable.

### Running the Test Runner Script

The repository now includes a **test runner** that automatically submits a Condor job for each chunk file placed in `cms_driver_run/Test_datasets`.  It determines whether a chunk corresponds to data (files whose name starts with `singlemu`) or MC and uses the appropriate JDL.

#### Prerequisites
* A valid CMS proxy (`voms-proxy-init -rfc -voms cms -valid 192:00`).
* The Condor environment (`condor_submit`, `condor_q`) available on the machine (e.g., CMSLPC).
* The driver scripts (`run_cmsdriver_data.sh` and `run_cmsdriver_mc.sh`) are executable – the test runner will set the executable bit for you.

#### Usage
```bash
cd cms_driver_run          # repository root → cms_driver_run directory
chmod +x test_runner_script.sh   # make sure the script is executable
./test_runner_script.sh   # submit all test chunks
```

The script will:
1. Iterate over every file in `Test_datasets/`.
2. Derive a `SampleName` from the filename (e.g., `singlemu0` for data or `ttbar-powheg` for MC).
3. Submit the job with `condor_submit`, passing `SampleName` and `InputFile` variables to the JDL.
4. Print a short status line for each submission and finally display the Condor queue with `condor_q`.

After the submissions finish, you can monitor the jobs with the usual Condor tools (`condor_q`, `condor_status`, `condor_tail`).  Output files will be copied to the EOS locations defined in the driver scripts, just like the regular `runner_script.sh` workflow.

## Running With CRAB

The CRAB helper reads a YAML file from `miniAOD+SIM_sample_query/`, gathers files for each DAS dataset using `dasgoclient`, chunks them with `get_chunks`, generates one cmsRun config per chunk, and writes one CRAB config per chunk.

Create MC CRAB configs without submitting:

```bash
cd crab_run
python3 submit_crab_nanoaod.py ../miniAOD+SIM_sample_query/muon_2024_miniAODSIM_MC.yaml --mc --files-per-chunk 5
```

Create data CRAB configs without submitting:

```bash
cd crab_run
python3 submit_crab_nanoaod.py ../miniAOD+SIM_sample_query/muon_2024_miniAOD_DATA.yaml --data --files-per-chunk 5
```

Submit as the configs are created by adding `--submit`:

```bash
python3 submit_crab_nanoaod.py ../miniAOD+SIM_sample_query/muon_2024_miniAODSIM_MC.yaml --mc --files-per-chunk 5 --submit
```

The generated jobs use `crab_projects/<requestName>` as their CRAB work area.
After submission, manage all generated projects from `crab_run/` without
re-running the DAS queries:

```bash
python3 submit_crab_nanoaod.py --action status
python3 submit_crab_nanoaod.py --action resubmit
python3 submit_crab_nanoaod.py --action getoutput
```

`--action submit` is equivalent to `--submit`. The status action includes
`--verboseErrors`, matching the standard CRAB troubleshooting workflow.

Useful options:

- `--max-files N`: limit DAS output for testing.
- `--storage-site T3_US_FNALLPC`: set CRAB storage site.
- `--out-lfn-dir-base /store/group/lpcjm/$USER/cms_nanoaod`: set output LFN base.
- `--output-dir generated`: choose where generated CRAB configs and psets are written.

CRAB output LFNs are written below `<out-lfn-dir-base>/{data,mc}/<yaml-header>/`, matching the Condor layout.

Run CRAB commands from an initialized CMSSW area where `MyAnalysis/JetTools` has already been copied into `$CMSSW_BASE/src` and built with `scram b`. CRAB packages that CMSSW area for remote jobs; the helper ships only the generated file list and `cmsskim_customize.py` as extra job inputs.

Use a valid CMS grid proxy:

```bash
voms-proxy-init -rfc -voms cms -valid 192:00
```

## Notes

- `SetupSkim_HLTSingleMuonOneFatJet` applies the single-muon HLT and at least one AK8 fat-jet skim.
- `SetupGloParTForAK8Subjets` updates the existing packed soft-drop subjet table with GloParT variables.
- `SetupAK8ReclusterSubjets` adds the raw CA R=0.8 declustered subjet branches as a `FatJet` extension table.
