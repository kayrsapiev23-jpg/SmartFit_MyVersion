"""Deterministic, account-data-based SmartFit fitness coach features.

No remote AI provider; fitness education, not medical advice.
This module never invents completed workout sessions or performance metrics.
"""
from datetime import date, timedelta
import re


def classify_coach_intent(message: str) -> str | None:
    """Recognize requests for data-grounded features; leave open-ended chat to AI."""
    text = re.sub(r'\s+', ' ', message.casefold()).strip()
    if not text:
        return None
    # Specific requests for training history or progress come first.
    progress = (
        r'\b(progress|workout history|training history|logged workouts|my workouts|'
        r'workout stats|track my progress|analy[sz]e|statistics|sessions logged)\b|'
        r'прогресс|истори[яию]|статистик|анализир|проанализир|'
        r'жаттығу тарих|прогрессім|прогрессин|нәтиже|талдап|талдау'
    )
    if re.search(progress, text):
        return 'progress'
    plan = (
        r'\b(workout plan|training plan|exercise plan|weekly plan|training routine|'
        r'workout routine|create a routine|make a routine|create.*workout|'
        r'plan.*workout|routine.*day|program for.*day|3.day.*plan|'
        r'plan for.*day|(?:create|make|build|generate|give me) (?:my |a )?(?:training |workout )?(?:plan|routine))\b|'
        r'план трениров|план занят|программ[ауеы] трениров|состав[ьи].*план|'
        r'тренировочн.*план|жаттығу жоспар|жаттығу бағдарлам|жоспар құрастыр|'
        r'апталық жоспар'
    )
    if re.search(plan, text):
        return 'plan'
    return None


EXERCISES = {
    'Home': {
        'A': [
            ('Chair squat', '6–10 reps'),
            ('Wall or counter push-up', '6–10 reps'),
            ('Standing hip hinge', '8–10 reps'),
            ('Bird-dog (slow and steady)', '6 each side'),
        ],
        'B': [
            ('Step-up on a stable low step', '6–8 each leg'),
            ('Glute bridge', '8–12 reps'),
            ('Wall push-up', '6–10 reps'),
            ('Dead bug', '6 each side'),
        ],
        'C': [
            ('Chair squat', '6–10 reps'),
            ('Standing calf raise', '10–12 reps'),
            ('Incline push-up at a stable surface', '6–10 reps'),
            ('Bird-dog', '6 each side'),
        ],
    },
    'No equipment': {
        'A': [
            ('Squat to a comfortable depth', '6–10 reps'),
            ('Wall push-up', '6–10 reps'),
            ('Hip hinge', '8–10 reps'),
            ('Bird-dog', '6 each side'),
        ],
        'B': [
            ('Standing reverse step', '6 each leg'),
            ('Glute bridge', '8–12 reps'),
            ('Wall push-up', '6–10 reps'),
            ('Dead bug', '6 each side'),
        ],
        'C': [
            ('Squat to a comfortable depth', '6–10 reps'),
            ('Calf raise', '10–12 reps'),
            ('Standing hip hinge', '8–10 reps'),
            ('Bird-dog', '6 each side'),
        ],
    },
    'Gym': {
        'A': [
            ('Leg press (light load)', '8–10 reps'),
            ('Seated cable row (light load)', '8–10 reps'),
            ('Chest press machine (light load)', '8–10 reps'),
            ('Dead bug', '6 each side'),
        ],
        'B': [
            ('Bodyweight squat', '8–10 reps'),
            ('Lat pulldown (light load)', '8–10 reps'),
            ('Glute bridge', '8–12 reps'),
            ('Bird-dog', '6 each side'),
        ],
        'C': [
            ('Leg press (light load)', '8–10 reps'),
            ('Seated row (light load)', '8–10 reps'),
            ('Chest press machine (light load)', '8–10 reps'),
            ('Standing calf raise', '10–12 reps'),
        ],
    },
}


def create_workout_plan(profile: dict) -> str:
    if not profile:
        return 'No SmartFit fitness profile is saved yet. Complete Profile & settings, then generate a plan.'
    experience = str(profile.get('experience') or 'Beginner')
    goal = str(profile.get('fitness_goal') or 'General fitness')
    equipment = str(profile.get('equipment') or 'No equipment')
    if equipment not in EXERCISES:
        equipment = 'No equipment'
    try:
        days = max(1, min(7, int(profile.get('training_days') or 3)))
    except (ValueError, TypeError):
        days = 3

    # Workouts are spread across the week, without scheduling intense strength
    # sessions on seven consecutive days. The remaining sessions are gentle.
    if days == 1:
        slots = ['Mon']
    elif days == 2:
        slots = ['Mon', 'Thu']
    elif days == 3:
        slots = ['Mon', 'Wed', 'Fri']
    elif days == 4:
        slots = ['Mon', 'Tue', 'Thu', 'Sat']
    elif days == 5:
        slots = ['Mon', 'Tue', 'Wed', 'Fri', 'Sun']
    elif days == 6:
        slots = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    else:
        slots = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    # 3 strength days with recovery gaps; flexible moderate activity in between.
    if days <= 3:
        strength_indices = set(range(days))
    elif days == 4:
        strength_indices = {0, 2, 3}
    elif days == 5:
        strength_indices = {0, 2, 3}
    else:
        strength_indices = {0, 2, 4}
    sets = 2 if experience == 'Beginner' else 3
    rest = '60–90 sec' if experience == 'Beginner' else '60–120 sec'
    lines = [
        'SMARTFIT PERSONAL WORKOUT PLAN (guided, based on your saved profile)',
        f'Goal: {goal} | Experience: {experience} | Equipment: {equipment} | Days/week: {days}',
        f'Start gently: 3–5 min easy warm-up. For strength exercises: {sets} sets each; rest {rest} between sets.',
    ]
    strength_number = 0
    for index, weekday in enumerate(slots):
        if index in strength_indices:
            key = 'ABC'[strength_number % 3]
            strength_number += 1
            lines.append(f'\n{weekday} — Full-body strength ({key}):')
            for exercise, reps in EXERCISES[equipment][key]:
                lines.append(f'• {exercise} — {sets} × {reps}')
            if goal == 'Improve endurance':
                lines.append('• Optional: 8–12 min comfortable walking or easy cycling')
            elif goal == 'Improve flexibility':
                lines.append('• 5–8 min gentle stretching and mobility after the session')
            elif goal == 'Stay active':
                lines.append('• Finish with a short comfortable walk if you feel like it')
        else:
            if goal == 'Improve flexibility':
                lines.extend([f'\n{weekday} — Easy mobility:',
                              '• 10–20 min gentle movement and comfortable stretching',
                              '• Balance practice — 2 × 20 sec each side'])
            else:
                lines.extend([f'\n{weekday} — Easy recovery / endurance:',
                              '• 15–25 min comfortable walking or easy cycling',
                              '• 5 min light mobility; keep the effort conversational'])
    lines.append('\nWhy this fits: the days and equipment match your profile. Strength sessions alternate with recovery or gentler activity where possible; exercises are adjustable for your experience.')
    lines.append('Use smooth, controlled movements; stop if an exercise hurts and ask a qualified professional about persistent pain. You can take extra rest days. This is general fitness education, not medical advice.')
    return '\n'.join(lines)


def analyze_workout_progress(profile: dict, sessions: list[dict], exercise_rows: list[dict], *, today: date | None = None) -> str:
    """Summarize only logged workouts, no guessed progress or body statistics."""
    today = today or date.today()
    if not profile:
        return 'Save your training preferences on Profile & settings to get a personalized SmartFit progress summary.'
    clean = []
    for row in sessions:
        try:
            when = date.fromisoformat(str(row['completed_on']))
        except (KeyError, TypeError, ValueError):
            continue
        if when <= today:
            clean.append((when, str(row.get('title') or 'Workout')[:70]))
    clean.sort(reverse=True)
    this_week_start = today - timedelta(days=today.weekday())
    last_week_start = this_week_start - timedelta(days=7)
    week_count = sum(this_week_start <= d <= today for d, _ in clean)
    last_week_count = sum(last_week_start <= d < this_week_start for d, _ in clean)
    month_count = sum(d.year == today.year and d.month == today.month for d, _ in clean)
    last_28 = sum(today-timedelta(days=27) <= d <= today for d, _ in clean)
    try:
        target = max(1,min(7,int(profile.get('training_days') or 3)))
    except (TypeError,ValueError):
        target = 3
    lines = [
        'SMARTFIT WORKOUT PROGRESS (from your saved workout tracker)',
        f'Total logged sessions: {len(clean)}',
        f'This week: {week_count} session(s) | Last week: {last_week_count}',
        f'This month: {month_count} | Last 28 days: {last_28}',
        f'Your profile training preference: {target} day(s) per week.',
    ]
    if not clean:
        lines.append('No workout sessions have been recorded yet. Complete a session in Workout Tracker to start building your history.')
        lines.append('There is not enough data to evaluate strength or endurance improvements yet.')
    else:
        lines.append('Latest recorded sessions:')
        for when, title in clean[:5]:
            lines.append(f'• {when.isoformat()} — {title}')
        if exercise_rows:
            names = [str(row.get('exercise') or '').strip()[:60] for row in exercise_rows]
            if any(names):
                lines.append('Recorded exercises: ' + ', '.join(name for name in names if name) + '.')
        lines.append('These counts show logging consistency, not proof of muscle or strength gains. Keep recording your sessions and adjust gradually to comfort and recovery.')
    return '\n'.join(lines)
