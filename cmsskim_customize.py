# File: CMS_SkimmingConfig.py
# Place this file in your working directory on lxplus
# This module contains custom functions for CMS skimming and weight table setup

import FWCore.ParameterSet.Config as cms
from HLTrigger.HLTfilters.hltHighLevel_cfi import hltHighLevel

def SetupGloParTForAK8Subjets(process):
    """
    Setup GloParT for AK8 subjets by updating the jet collection and adding relevant variables to the subJetTable.
    """
    from PhysicsTools.NanoAOD.common_cff import Var

    pfLabel = "packedPFCandidates"
    pvLabel = "offlineSlimmedPrimaryVertices"
    svLabel = "slimmedSecondaryVertices"
    muLabel = "slimmedMuons"
    elLabel = "slimmedElectrons"
    gpLabel = "prunedGenParticles"

    from RecoBTag.ONNXRuntime.pfGlobalParticleTransformerAK8_cff import _pfGlobalParticleTransformerAK8JetTagsAll as pfGlobalParticleTransformerAK8JetTagsAll
    btagDiscriminatorsAK8Subjets = cms.PSet(names = cms.vstring(
        pfGlobalParticleTransformerAK8JetTagsAll 
    )
    )

    from PhysicsTools.PatAlgos.tools.jetTools import  updateJetCollection
    updateJetCollection(process,
    labelName = "AK8PFPuppiSoftDropSubjets",
    postfix = 'WithGloParT',
    jetSource = cms.InputTag("slimmedJetsAK8PFPuppiSoftDropPacked","SubJets"),
    pfCandidates = cms.InputTag(pfLabel),
    pvSource = cms.InputTag(pvLabel),
    svSource = cms.InputTag(svLabel),
    muSource = cms.InputTag(muLabel),
    elSource = cms.InputTag(elLabel),
    printWarning = False,
    jetCorrections = ('AK4PFPuppi', cms.vstring(['L1FastJet', 'L2Relative', 'L3Absolute', 'L2L3Residual']), 'None'),
    #Important. Preserve the original order as in ("slimmedJetsAK8PFPuppiSoftDropPacked","SubJets") as the keys of the associated subjets in the AK8 jets
    #are based on the original order.
    sortByPt = False,
    btagDiscriminators = btagDiscriminatorsAK8Subjets.names.value() if btagDiscriminatorsAK8Subjets is not None else ['None'],
    )

    process.subJetTable.src = cms.InputTag("selectedUpdatedPatJetsAK8PFPuppiSoftDropSubjetsWithGloParT")
    process.subJetTable.variables.globalParT3_Xbb = Var("bDiscriminator('pfGlobalParticleTransformerAK8JetTags:probXbb')",float,doc="Mass-decorrelated GlobalParT-3 X->bb score. Note: For sig vs bkg (e.g. bkg=QCD) tagging, use sig/(sig+bkg) to construct the discriminator",precision=10)
    process.subJetTable.variables.globalParT3_Xcc = Var("bDiscriminator('pfGlobalParticleTransformerAK8JetTags:probXcc')",float,doc="Mass-decorrelated GlobalParT-3 X->cc score",precision=10)
    process.subJetTable.variables.globalParT3_Xcs = Var("bDiscriminator('pfGlobalParticleTransformerAK8JetTags:probXcs')",float,doc="Mass-decorrelated GlobalParT-3 X->cs score",precision=10)
    process.subJetTable.variables.globalParT3_Xqq = Var("bDiscriminator('pfGlobalParticleTransformerAK8JetTags:probXqq')",float,doc="Mass-decorrelated GlobalParT-3 X->qq (ss/dd/uu) score",precision=10)
    process.subJetTable.variables.globalParT3_QCD = Var("bDiscriminator('pfGlobalParticleTransformerAK8JetTags:probQCD')",float,doc="Mass-decorrelated GlobalParT-3 QCD score.",precision=10)
    process.subJetTable.variables.globalParT3_massCorrX2p = Var("bDiscriminator('pfGlobalParticleTransformerAK8JetTags:massCorrX2p')",float,doc="GlobalParT-3 mass regression corrector with respect to the original jet mass, optimised for resonance 2-prong (bb/cc/cs/ss/qq) jets. Use (massCorrX2p * mass * (1 - rawFactor)) to get the regressed mass",precision=10)
    process.subJetTable.variables.globalParT3_massCorrGeneric = Var("bDiscriminator('pfGlobalParticleTransformerAK8JetTags:massCorrGeneric')",float,doc="GlobalParT-3 mass regression corrector with respect to the original jet mass, optimised for generic jet cases. Use (massCorrGeneric * mass * (1 - rawFactor)) to get the regressed mass",precision=10)
    process.subJetTable.variables.globalParT3_withMassTopvsQCD = Var("bDiscriminator('pfGlobalParticleTransformerAK8JetTags:probWithMassTopvsQCD')",float,doc="GlobalParT-3 tagger (w/mass) Top vs QCD discriminator",precision=10)
    process.subJetTable.variables.globalParT3_withMassWvsQCD = Var("bDiscriminator('pfGlobalParticleTransformerAK8JetTags:probWithMassWvsQCD')",float,doc="GlobalParT-3 tagger (w/mass) W vs QCD discriminator",precision=10)
    process.subJetTable.variables.globalParT3_withMassZvsQCD = Var("bDiscriminator('pfGlobalParticleTransformerAK8JetTags:probWithMassZvsQCD')",float,doc="GlobalParT-3 tagger (w/mass) Z vs QCD discriminator",precision=10)

    return process


def SetupSkimForMC_AlwaysRunWeightsTable(process):
    """
    Setup MC skimming to always run the weights table
    """
    process.genWeightsTableSequence = cms.Sequence(process.genWeightsTable)
    process.genWeightsTablePath = cms.Path(process.genWeightsTableSequence)
    process.schedule.insert(0, process.genWeightsTablePath)
    return process


def SetupSkim_HLTSingleMuonOneFatJet(process):
    """
    Setup skimming with HLT single muon trigger and at least one fat jet
    """
    
    trigPathsSingleMuon = [
        'HLT_IsoMu24_v*',
        'HLT_Mu50_v*',
        'HLT_HighPtTkMu100_v*',
        'HLT_CascadeMu100_v*'
    ]
    
    # Setup HLT part of the skim
    process.HLTSingleMuonFilter = hltHighLevel.clone()
    process.HLTSingleMuonFilter.TriggerResultsTag = cms.InputTag("TriggerResults", "", "HLT")
    process.HLTSingleMuonFilter.HLTPaths = cms.vstring(trigPathsSingleMuon)
    process.HLTSingleMuonFilter.throw = cms.bool(False)

    # Setup offline fatjet part of the skim
    process.selectedSlimmedJetsAK8 = cms.EDFilter("CandViewRefSelector",
        src=cms.InputTag("slimmedJetsAK8"),
        cut=cms.string("abs(eta) < 3.0")
    )

    process.selectedSlimmedJetsAK8CountFilter = cms.EDFilter("CandViewCountFilter",
        src=cms.InputTag("selectedSlimmedJetsAK8"),
        minNumber=cms.uint32(1)
    )

    process.skimHLTSingleMuonOneFatJetSequence = cms.Sequence(
        process.HLTSingleMuonFilter * 
        process.selectedSlimmedJetsAK8 * 
        process.selectedSlimmedJetsAK8CountFilter
    )
    process.SKIMHLTSingleMuonOneFatJet = cms.Path(process.skimHLTSingleMuonOneFatJetSequence)
    process.schedule.insert(0, process.SKIMHLTSingleMuonOneFatJet)

    # Configure output module to apply skim
    if hasattr(process, "NANOEDMAODoutput") or hasattr(process, "NANOAODoutput"):
        process.NANOAODoutput.SelectEvents = cms.untracked.PSet(
            SelectEvents=cms.vstring('SKIMHLTSingleMuonOneFatJet')
        )
    elif hasattr(process, "NANOEDMAODSIMoutput") or hasattr(process, "NANOAODSIMoutput"):
        process.NANOAODSIMoutput.SelectEvents = cms.untracked.PSet(
            SelectEvents=cms.vstring('SKIMHLTSingleMuonOneFatJet')
        )
        process = SetupSkimForMC_AlwaysRunWeightsTable(process)

    return process


def SetupAK8ReclusterSubjets(process):
    """
    Add raw_sj1/raw_sj2 branches to the FatJet table.

    The C++ module first reclusters each slimmedJetsAK8 jet with Cambridge-
    Aachen R=0.8 and then declusters the leading reclustered jet until the
    leading resolved two-prong split is found. raw_sj1 is the larger-pT prong.
    """

    process.ak8ReclusteredSubjetTable = cms.EDProducer(
        "AK8ReclusterTableProducer",
        fatJets=cms.InputTag("slimmedJetsAK8"),
        name=cms.string("FatJet"),
        doc=cms.string("raw_sj1 and raw_sj2 from CA R=0.8 declustering inside each slimmedJetsAK8 jet"),
        algorithm=cms.string("CambridgeAachen"),
        rParam=cms.double(0.8),
        minSubjetPt=cms.double(1.0),
        maxSubjetAbsEta=cms.double(5.0),
        missingValue=cms.double(-99.0),
    )

    for sequence_name in ("nanoSequence", "nanoSequenceMC", "nanoSequenceFS"):
        if hasattr(process, sequence_name):
            getattr(process, sequence_name).insert(0, process.ak8ReclusteredSubjetTable)

    return process
