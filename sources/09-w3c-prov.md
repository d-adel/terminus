# W3C PROV-O (PROV Ontology)

**Title:** W3C PROV-O: The PROV Ontology

**URL:** https://www.w3.org/TR/prov-o/

**Version/Date:** W3C Recommendation; maintained at TR/prov-o

**Access:** Public W3C standard (no paywall)

**Source(s):** W3C official technical specification.

## Three Core Classes

- **Entity:** "A physical, digital, conceptual, or other kind of thing with some fixed aspects; entities may be real or imaginary"
- **Activity:** "Something that occurs over a period of time and acts upon or with entities; it may include consuming, processing, transforming, modifying, relocating, using, or generating entities"
- **Agent:** "Something that bears some form of responsibility for an activity taking place, for the existence of an entity, or for another agent's activity"

## Core Relations

- **used:** "Describes entities utilized during an activity"
- **wasGeneratedBy:** "Links an entity to the activity that produced it; completion of production of a new entity by an activity"
- **wasDerivedFrom:** "Connects one entity to another entity from which it was transformed, updated, or constructed"
- **wasAttributedTo:** "Assigns responsibility for an entity to an agent; indicates responsibility of an agent for an entity's existence"
- **wasAssociatedWith:** "Connects activities to agents bearing responsibility; agent had responsibility in the activity"
- **actedOnBehalfOf:** "Represents delegation between agents; agent A acts on behalf of agent B"

## Qualified Properties Pattern

- **prov:qualifiedUsage, qualifiedGeneration, qualifiedAssociation, qualifiedDelegation:** Properties allowing elaboration of core relations with contextual detail (roles, plans, times)
- **prov:atTime:** Specifies instantaneous event timing as xsd:dateTime
- **prov:hadRole:** Describes functional context of entities or agents in relations
- **prov:hadPlan:** References intended action sets for associations

## Supporting Concepts

- **Influence (prov:Influence):** Superclass capturing how resources affect one another; includes EntityInfluence, ActivityInfluence, AgentInfluence
- **prov:influencer:** References the resource whose influence is being qualified

## Notes

PROV-O is a complete, formal ontology maintained by W3C. Definitions are normative and available without restriction. The specification supports interoperable provenance representation across systems.
