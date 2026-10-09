"""Conservative caption observations; detection counts never establish an event."""
import re

LABELS = {
    'cyclist_passage_review':'Cyclist passage',
    'curb_use_review':'Curb use',
    'crossing_review':'Crossing activity',
    'queue_review':'Slow traffic',
}

def observations(clip):
    text = clip.get('caption', '').lower()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    found = {}
    for sentence in sentences:
        if re.search(r'\b(no|not|without)\b', sentence):
            continue
        vehicle = bool(re.search(r'\b(cars?|vehicles?|trucks?|vans?|suv|sedan|taxi|taxis)\b', sentence))
        if vehicle and re.search(r'\b(parked|stopped)\b', sentence) and re.search(r'\b(curbs?|(?:left|right) side of (?:the )?(?:street|road))\b', sentence):
            found.setdefault('curb_use_review', sentence)
        if re.search(r'\b(pedestrians?|people|persons?)\b.{0,60}\b(crossing|crosswalk|crosses)\b', sentence):
            found.setdefault('crossing_review', sentence)
        if re.search(r'\b(cars|vehicles|taxis|traffic)\b.{0,45}\b(moving slowly|slow-moving|stopped or moving slowly|queued|backed up)\b', sentence):
            found.setdefault('queue_review', sentence)
        if ('cyclist' in text or 'bicycle' in text or 'bike lane' in text) and re.search(r'\b(partially blocking|obstructing|narrowing|blocking)\b.{0,55}\b(lane|road|street|space|passage)\b', sentence):
            found.setdefault('cyclist_passage_review', sentence)
    return found
