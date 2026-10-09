"""Admission boundary between model diagnoses and archive-grounded movement events."""
import hashlib
import json
import re

VERSION = 'obstructed-passage-v1'
SYSTEM_PROMPT = '''You diagnose street bottlenecks from indexed video reasoning captions.
Return only JSON: {"findings":[{"obstruction":[{"segment_number":3,"quote":"exact supplied quotation"}],"movement_effect":[{"segment_number":4,"quote":"exact supplied quotation"}]}]}.
Use ONLY the allowed quotation objects supplied in the question, unchanged, under their supplied roles.
Require a physical path obstruction AND an actual observed maneuver around/past that obstruction.
Associate the same obstruction with the maneuver; unrelated activity is not evidence.
Parked vehicles alone, object counts, normal passing, stopped riders, and red-light queues are not bottlenecks.
At most three findings; at most six quotations per role. Return {"findings":[]} when unsupported.
Do not supply actions, metrics, invented quotations, legal judgments, delays, distances or capacity claims.'''


def sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text or '') if s.strip()]


def qualifies(quote, role):
    text = quote.lower()
    if re.search(r'\b(no|not|without|could|might|potential|appears?|suggests?)\b', text):
        return False
    if role == 'obstruction':
        return bool(re.search(r'\b(car|sedan|vehicle|truck|van|barrier|barricade|cones?)\b', text)
                    and re.search(r'\b(block\w*|obstruct\w*|narrow\w*)\b.{0,75}\b(lane|path|road|roadway|street|space)\b', text))
    return bool(re.search(r'\b(cyclist|rider|camera|ego|vehicle)\b', text)
                and re.search(r'\b(maneuv\w*|navigat\w*|steer\w*|divert\w*|swerve\w*)\b.{0,55}\b(around|past)\b', text)
                and re.search(r'\b(parked|stopped|obstruction|truck|sedan|van|barrier|barricade)\b', text))


def allowed_claims(clips):
    return {role: [{'segment_number':c['segment_number'], 'quote':s}
                   for c in clips for s in sentences(c['caption']) if qualifies(s, role)]
            for role in ('obstruction', 'movement_effect')}


def parse_diagnosis(answer):
    if not isinstance(answer, str) or len(answer) > 24000:
        raise ValueError('Invalid diagnosis')
    match = re.fullmatch(r'\s*```(?:json)?\s*\n?(.*?)\n?```\s*', answer, re.S)
    data = json.loads(match.group(1) if match else answer)
    if not isinstance(data, dict) or set(data) != {'findings'} or not isinstance(data['findings'], list) or len(data['findings']) > 3:
        raise ValueError('Invalid diagnosis')
    return data['findings']


def validate_findings(answer, clips):
    """Model selects supplied evidence; backend owns identity, intervals and episode count."""
    parents = {c['original_video'] for c in clips}
    if len(parents) != 1 or len(clips) > 6:
        raise ValueError('Invalid evidence scope')
    known = {c['segment_number']:c for c in clips}
    if len(known) != len(clips):
        raise ValueError('Duplicate segment slots')
    allowed = allowed_claims(clips)
    admitted = []
    for finding in parse_diagnosis(answer):
        if not isinstance(finding, dict) or set(finding) != {'obstruction','movement_effect'}:
            raise ValueError('Invalid finding')
        selected = {}
        for role in allowed:
            claims = finding[role]
            if not isinstance(claims, list) or not 1 <= len(claims) <= 6:
                raise ValueError('Missing claim')
            for claim in claims:
                # Some VSS synthesizers serialize segment numbers as decimal strings.
                # Normalize only that lossless representation before exact membership.
                if isinstance(claim, dict) and isinstance(claim.get('segment_number'), str) and re.fullmatch(r'[1-9][0-9]?', claim['segment_number']):
                    claim['segment_number'] = int(claim['segment_number'])
                if not isinstance(claim, dict) or set(claim) != {'segment_number','quote'} or type(claim['segment_number']) is not int or claim not in allowed[role]:
                    raise ValueError('Unsupported citation')
            selected[role] = claims
        # Quotations must concern a local sequence, not two distant activities.
        obstruction_clips = [known[c['segment_number']] for c in selected['obstruction']]
        movement_clips = [known[c['segment_number']] for c in selected['movement_effect']]
        if any(not any(abs(c['start_sec']-o['start_sec']) <= 10 for o in obstruction_clips) for c in movement_clips):
            raise ValueError('Unrelated intervals')
        admitted.append(selected)
    # Merge duplicate/adjacent selections into one local episode. Include canonical
    # eligible quotations in that neighborhood so stable IDs survive model ordering.
    events = []
    for finding in admitted:
        starts = [known[c['segment_number']]['start_sec'] for role in finding for c in finding[role]]
        events.append({'start':min(starts),'end':max(known[c['segment_number']]['end_sec'] for role in finding for c in finding[role]),'claims':finding})
    merged = []
    for event in sorted(events, key=lambda e:e['start']):
        if merged and event['start'] <= merged[-1]['end'] + 5:
            previous = merged[-1]
            previous['end'] = max(previous['end'], event['end'])
            for role in allowed:
                previous['claims'][role] += event['claims'][role]
        else:
            merged.append(event)
    results = []
    for event in merged:
        claims = []
        for role in allowed:
            for claim in allowed[role]:
                c = known[claim['segment_number']]
                if c['start_sec'] <= event['end'] + 5 and c['end_sec'] >= event['start'] - 5:
                    claims.append({'role':role, 'segment_id':c['id'], **claim})
        # Identity follows the earliest canonical movement segment in this episode.
        first = min(known[c['segment_number']]['start_sec'] for c in claims if c['role']=='movement_effect')
        identity = f'{VERSION}:{next(iter(parents))}:{first}'
        results.append({'id':hashlib.sha256(identity.encode()).hexdigest()[:16],
                        'type':'obstructed_passage', 'claims':claims,
                        'subtype':'temporary_barrier' if any(re.search(r'\b(barrier|barricade|cones?)\b', c['quote'], re.I) for c in claims if c['role']=='obstruction') else 'parked_vehicle',
                        'basis':'indexed_reasoning_with_validated_quotes',
                        'uncertainties':['The maneuver is described in indexed captions; no calibrated path geometry is available.',
                                         'Delay, legal parking status, street width and recurrence are not established.']})
    return results
