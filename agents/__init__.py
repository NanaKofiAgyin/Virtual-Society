"""Agents package: base agent, genomes, life cycle, animals, human utility brain, humans."""

from agents.animal import AnimalAgent, SpeciesConfig, load_species, spawn_animals
from agents.base import ALL_ACTIONS, Action, ActionType, Agent, Needs
from agents.genome import (
    GENES,
    Genome,
    Phenotype,
    crossover,
    express_phenotype,
    genetic_distance,
    mutate,
    random_genome,
)
from agents.human import HumanAgent, Persona
from agents.lifecycle import (
    TICKS_PER_YEAR,
    DeathCause,
    FamilyTree,
    LifeStage,
    can_mate_animals,
    can_pair_humans,
    child_learn_from_adults,
    compute_life_stage,
    spawn_human_child,
)
from agents.memory import Memory, MemoryStream, score_importance

__all__ = [
    "ALL_ACTIONS", "Action", "ActionType", "Agent", "AnimalAgent", "DeathCause",
    "FamilyTree", "GENES", "Genome", "HumanAgent", "LifeStage", "Memory",
    "MemoryStream", "Needs", "Persona", "Phenotype", "SpeciesConfig", "TICKS_PER_YEAR",
    "can_mate_animals", "can_pair_humans", "child_learn_from_adults",
    "compute_life_stage", "crossover", "express_phenotype", "genetic_distance",
    "load_species", "mutate", "random_genome", "score_importance", "spawn_animals",
    "spawn_human_child",
]
