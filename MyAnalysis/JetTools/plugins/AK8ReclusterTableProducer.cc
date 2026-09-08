#include <algorithm>
#include <cmath>
#include <memory>
#include <string>
#include <vector>

#include "DataFormats/Candidate/interface/Candidate.h"
#include "DataFormats/Candidate/interface/CandidateFwd.h"  // defines reco::CandidateBaseRefVector
#include "DataFormats/Common/interface/RefToBaseVector.h"
#include "DataFormats/Common/interface/View.h"
#include "DataFormats/NanoAOD/interface/FlatTable.h"
#include "DataFormats/PatCandidates/interface/Jet.h"
#include "FWCore/Framework/interface/Event.h"
#include "FWCore/Framework/interface/Frameworkfwd.h"
#include "FWCore/Framework/interface/MakerMacros.h"
#include "FWCore/Framework/interface/stream/EDProducer.h"
#include "FWCore/ParameterSet/interface/ConfigurationDescriptions.h"
#include "FWCore/ParameterSet/interface/ParameterSet.h"
#include "FWCore/ParameterSet/interface/ParameterSetDescription.h"
#include "FWCore/Utilities/interface/Exception.h"
#include "fastjet/ClusterSequence.hh"
#include "fastjet/PseudoJet.hh"

class AK8ReclusterTableProducer : public edm::stream::EDProducer<> {
public:
  explicit AK8ReclusterTableProducer(const edm::ParameterSet&);
  ~AK8ReclusterTableProducer() override = default;

  static void fillDescriptions(edm::ConfigurationDescriptions&);

private:
  struct RawSubjetPair {
    bool hasSj1 = false;
    bool hasSj2 = false;
    fastjet::PseudoJet sj1;
    fastjet::PseudoJet sj2;
  };

  void produce(edm::Event&, const edm::EventSetup&) override;
  fastjet::JetAlgorithm jetAlgorithm() const;
  RawSubjetPair findRawSubjets(const fastjet::PseudoJet&) const;

  // The module consumes a generic collection of reco::Candidate objects.
  // Using edm::View<reco::Candidate> works for both the output of a
  // CandViewRefSelector (which yields a RefVector) and a plain pat::Jet
  // collection, avoiding the DictionaryNotFound error that arises when the
  // token type does not have a generated dictionary.
  const edm::EDGetTokenT<edm::View<reco::Candidate>> fatJetsToken_;
  const std::string name_;
  const std::string doc_;
  const std::string algorithm_;
  const double rParam_;
  const double minSubjetPt_;
  const double maxSubjetAbsEta_;
  const double missingValue_;
};

AK8ReclusterTableProducer::AK8ReclusterTableProducer(const edm::ParameterSet& cfg)
    : fatJetsToken_(consumes<edm::View<reco::Candidate>>(cfg.getParameter<edm::InputTag>("fatJets"))),
      name_(cfg.getParameter<std::string>("name")),
      doc_(cfg.getParameter<std::string>("doc")),
      algorithm_(cfg.getParameter<std::string>("algorithm")),
      rParam_(cfg.getParameter<double>("rParam")),
      minSubjetPt_(cfg.getParameter<double>("minSubjetPt")),
      maxSubjetAbsEta_(cfg.getParameter<double>("maxSubjetAbsEta")),
      missingValue_(cfg.getParameter<double>("missingValue")) {
  produces<nanoaod::FlatTable>();
}

fastjet::JetAlgorithm AK8ReclusterTableProducer::jetAlgorithm() const {
  if (algorithm_ == "CambridgeAachen" || algorithm_ == "CA" || algorithm_ == "cambridge") {
    return fastjet::cambridge_algorithm;
  }
  if (algorithm_ == "AntiKt" || algorithm_ == "anti-kt" || algorithm_ == "ak") {
    return fastjet::antikt_algorithm;
  }
  if (algorithm_ == "Kt" || algorithm_ == "kt") {
    return fastjet::kt_algorithm;
  }
  throw cms::Exception("Configuration") << "Unsupported reclustering algorithm '" << algorithm_
                                        << "'. Use CambridgeAachen, AntiKt, or Kt.";
}

AK8ReclusterTableProducer::RawSubjetPair AK8ReclusterTableProducer::findRawSubjets(
    const fastjet::PseudoJet& caJet) const {
  RawSubjetPair result;
  fastjet::PseudoJet current = caJet;

  fastjet::PseudoJet parent1;
  fastjet::PseudoJet parent2;
  while (current.has_parents(parent1, parent2)) {
    if (parent2.pt() > parent1.pt()) {
      std::swap(parent1, parent2);
    }

    if (parent2.pt() >= minSubjetPt_) {
      result.hasSj1 = true;
      result.hasSj2 = true;
      result.sj1 = parent1;
      result.sj2 = parent2;
      return result;
    }

    current = parent1;
  }

  if (current.pt() >= minSubjetPt_) {
    result.hasSj1 = true;
    result.sj1 = current;
  }
  return result;
}

void AK8ReclusterTableProducer::produce(edm::Event& event, const edm::EventSetup&) {
  edm::Handle<edm::View<reco::Candidate>> fatJetRefs;
  event.getByToken(fatJetsToken_, fatJetRefs);

  const auto nFatJets = fatJetRefs->size();
  std::vector<float> rawSj1Pt(nFatJets, missingValue_);
  std::vector<float> rawSj1Eta(nFatJets, missingValue_);
  std::vector<float> rawSj1Phi(nFatJets, missingValue_);
  std::vector<float> rawSj1Mass(nFatJets, missingValue_);
  std::vector<int> rawSj1NConstituents(nFatJets, 0);
  std::vector<float> rawSj2Pt(nFatJets, missingValue_);
  std::vector<float> rawSj2Eta(nFatJets, missingValue_);
  std::vector<float> rawSj2Phi(nFatJets, missingValue_);
  std::vector<float> rawSj2Mass(nFatJets, missingValue_);
  std::vector<int> rawSj2NConstituents(nFatJets, 0);

  const fastjet::JetDefinition jetDef(jetAlgorithm(), rParam_);

  for (size_t fatJetIdx = 0; fatJetIdx < fatJetRefs->size(); ++fatJetIdx) {
    const reco::Candidate* cand = (*fatJetRefs)[fatJetIdx].get();
    if (cand == nullptr) {
      // Defensive: null/dangling ref. Leave this entry at missingValue_.
      continue;
    }

    const auto* fatJetPtr = dynamic_cast<const pat::Jet*>(cand);
    if (fatJetPtr == nullptr) {
      // Defensive: the underlying candidate isn't actually a pat::Jet.
      // Should not happen for selectedSlimmedJetsAK8, but avoids a crash
      // if the upstream selector's source collection ever changes type.
      continue;
    }
    const auto& fatJet = *fatJetPtr;

    std::vector<fastjet::PseudoJet> inputs;
    inputs.reserve(fatJet.numberOfDaughters());

    const auto daughterPtrs = fatJet.daughterPtrVector();
    if (!daughterPtrs.empty()) {
      for (const auto& daughter : daughterPtrs) {
        if (daughter.isNull() || !daughter.isAvailable()) {
          continue;
        }
        inputs.emplace_back(daughter->px(), daughter->py(), daughter->pz(), daughter->energy());
      }
    } else {
      for (size_t idx = 0; idx < fatJet.numberOfDaughters(); ++idx) {
        const auto* daughter = fatJet.daughter(idx);
        if (daughter == nullptr) {
          continue;
        }
        inputs.emplace_back(daughter->px(), daughter->py(), daughter->pz(), daughter->energy());
      }
    }

    if (inputs.empty()) {
      continue;
    }

    fastjet::ClusterSequence clusterSequence(inputs, jetDef);
    const auto caJets = fastjet::sorted_by_pt(clusterSequence.inclusive_jets(minSubjetPt_));
    if (caJets.empty()) {
      continue;
    }

    const auto rawSubjets = findRawSubjets(caJets.front());
    if (rawSubjets.hasSj1 && std::abs(rawSubjets.sj1.eta()) <= maxSubjetAbsEta_) {
      rawSj1Pt[fatJetIdx] = rawSubjets.sj1.pt();
      rawSj1Eta[fatJetIdx] = rawSubjets.sj1.eta();
      rawSj1Phi[fatJetIdx] = rawSubjets.sj1.phi_std();
      rawSj1Mass[fatJetIdx] = std::max(0.0, rawSubjets.sj1.m());
      rawSj1NConstituents[fatJetIdx] = static_cast<int>(rawSubjets.sj1.constituents().size());
    }
    if (rawSubjets.hasSj2 && std::abs(rawSubjets.sj2.eta()) <= maxSubjetAbsEta_) {
      rawSj2Pt[fatJetIdx] = rawSubjets.sj2.pt();
      rawSj2Eta[fatJetIdx] = rawSubjets.sj2.eta();
      rawSj2Phi[fatJetIdx] = rawSubjets.sj2.phi_std();
      rawSj2Mass[fatJetIdx] = std::max(0.0, rawSubjets.sj2.m());
      rawSj2NConstituents[fatJetIdx] = static_cast<int>(rawSubjets.sj2.constituents().size());
    }
  }

  auto table = std::make_unique<nanoaod::FlatTable>(static_cast<unsigned int>(nFatJets), name_, false, true);
  table->setDoc(doc_);
  table->addColumn<float>("raw_sj1_pt", rawSj1Pt, "leading-pT raw subjet pT from CA R=0.8 declustering", 10);
  table->addColumn<float>("raw_sj1_eta", rawSj1Eta, "leading-pT raw subjet eta from CA R=0.8 declustering", 12);
  table->addColumn<float>("raw_sj1_phi", rawSj1Phi, "leading-pT raw subjet phi from CA R=0.8 declustering", 12);
  table->addColumn<float>("raw_sj1_mass", rawSj1Mass, "leading-pT raw subjet mass from CA R=0.8 declustering", 10);
  table->addColumn<int>(
      "raw_sj1_nConstituents", rawSj1NConstituents, "number of AK8 constituents clustered into raw_sj1");
  table->addColumn<float>("raw_sj2_pt", rawSj2Pt, "subleading-pT raw subjet pT from CA R=0.8 declustering", 10);
  table->addColumn<float>("raw_sj2_eta", rawSj2Eta, "subleading-pT raw subjet eta from CA R=0.8 declustering", 12);
  table->addColumn<float>("raw_sj2_phi", rawSj2Phi, "subleading-pT raw subjet phi from CA R=0.8 declustering", 12);
  table->addColumn<float>("raw_sj2_mass", rawSj2Mass, "subleading-pT raw subjet mass from CA R=0.8 declustering", 10);
  table->addColumn<int>(
      "raw_sj2_nConstituents", rawSj2NConstituents, "number of AK8 constituents clustered into raw_sj2");

  event.put(std::move(table));
}

void AK8ReclusterTableProducer::fillDescriptions(edm::ConfigurationDescriptions& descriptions) {
  edm::ParameterSetDescription desc;
  // NOTE: "fatJets" must resolve to a collection that can be read as edm::View<reco::Candidate>
  // (e.g. the output of a CandViewRefSelector such as selectedSlimmedJetsAK8).
  desc.add<edm::InputTag>("fatJets", edm::InputTag("selectedSlimmedJetsAK8"));
  desc.add<std::string>("name", "FatJet");
  desc.add<std::string>("doc", "raw_sj1 and raw_sj2 from CA R=0.8 declustering inside each slimmedJetsAK8 jet");
  desc.add<std::string>("algorithm", "CambridgeAachen");
  desc.add<double>("rParam", 0.8);
  desc.add<double>("minSubjetPt", 1.0);
  desc.add<double>("maxSubjetAbsEta", 5.0);
  desc.add<double>("missingValue", -99.0);
  descriptions.add("ak8ReclusterTableProducer", desc);
}

DEFINE_FWK_MODULE(AK8ReclusterTableProducer);