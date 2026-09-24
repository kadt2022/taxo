"""Ce que Taxo comprend d'un commit : les faits introduits, retires ou modifies entre deux instantanes.

La comparaison porte sur l'identite canonique des faits (ADR 0002) : une preuve qui se deplace ne change
pas un fait. Les couvertures ne sont pas des changements ; elles disent ce qui reste non interprete.
"""
INTRODUCED, REMOVED, MODIFIED = 'INTRODUCED', 'REMOVED', 'MODIFIED'
_UNKNOWN_COVERAGE = {'NOT_INTERPRETED', 'READ_ERROR'}


def _describe(fact):
    if fact['kind'] == 'ABSENCE':
        return {'kind': 'ABSENCE', 'subject': fact['pattern']['value'], 'relation': None, 'object': None}
    return {'kind': fact['kind'], 'subject': fact['subject'], 'relation': fact.get('relation'),
            'object': fact.get('object')}


def _change(change, before=None, after=None):
    fact = after or before
    described = _describe(fact)
    result = {'change': change, 'kind': described['kind'], 'subject': described['subject'],
              'relation': described['relation'], 'status': fact['status'],
              'before': _describe(before)['object'] if before else None,
              'after': _describe(after)['object'] if after else None,
              'evidence_before': before.get('evidence', []) if before else [],
              'evidence_after': after.get('evidence', []) if after else []}
    if 'derivation' in fact:
        result['derivation'] = fact['derivation']
    return result


def unknowns(coverage):
    return sorted({fact['subject'] for fact in coverage if fact['coverage_type'] in _UNKNOWN_COVERAGE})


def compare(before, after, identity):
    """Changements entre deux listes de faits ; un meme sujet et une meme relation dont seul l'objet
    change forment un MODIFIED plutot qu'un couple retire / introduit."""
    before_by_id = {identity(fact): fact for fact in before}
    after_by_id = {identity(fact): fact for fact in after}
    removed = [before_by_id[key] for key in before_by_id.keys() - after_by_id.keys()]
    introduced = [after_by_id[key] for key in after_by_id.keys() - before_by_id.keys()]

    def slot(fact):
        return (fact['kind'], fact.get('subject'), fact.get('relation')) if fact['kind'] == 'ASSERTION' else None

    removed_slots, introduced_slots = {}, {}
    for fact in removed:
        removed_slots.setdefault(slot(fact), []).append(fact)
    for fact in introduced:
        introduced_slots.setdefault(slot(fact), []).append(fact)
    changes = []
    for key in removed_slots.keys() & introduced_slots.keys():
        if key is not None and len(removed_slots[key]) == 1 and len(introduced_slots[key]) == 1:
            changes.append(_change(MODIFIED, removed_slots.pop(key)[0], introduced_slots.pop(key)[0]))
    changes += [_change(REMOVED, before=fact) for facts in removed_slots.values() for fact in facts]
    changes += [_change(INTRODUCED, after=fact) for facts in introduced_slots.values() for fact in facts]
    order = {MODIFIED: 0, INTRODUCED: 1, REMOVED: 2}
    changes.sort(key=lambda item: (order[item['change']], item['subject'], item['relation'] or '',
                                   str(item['after'] or item['before'] or '')))
    unchanged = len(before_by_id.keys() & after_by_id.keys())
    return changes, unchanged
