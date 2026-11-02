"""SmartFit v2: private accounts and fitness tracking. No legacy demo records are exposed."""
import os, sqlite3, secrets, json, base64, calendar
from pathlib import Path
from datetime import datetime, date, timedelta
from contextlib import contextmanager
from urllib.parse import quote
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pwdlib import PasswordHash
from authlib.integrations.starlette_client import OAuth

ROOT=Path(__file__).resolve().parent
DB_PATH=Path(os.environ.get('SMARTFIT_DB_PATH',str(ROOT/'smartfit_private.db')))
DB_PATH.parent.mkdir(parents=True,exist_ok=True)
SECRET=os.getenv('SESSION_SECRET','')
if not SECRET:  # local development only; production must supply SESSION_SECRET
    SECRET=secrets.token_urlsafe(32)
app=FastAPI(title='SmartFit — Private Fitness Dashboard')
app.add_middleware(SessionMiddleware,secret_key=SECRET,same_site='lax',https_only=os.getenv('HTTPS_ONLY','0')=='1',max_age=86400*7)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
tpl=Jinja2Templates(directory=str(ROOT/'templates'))
hasher=PasswordHash.recommended()
oauth=OAuth()
GOOGLE_READY=bool(os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET'))
if GOOGLE_READY:
    oauth.register(name='google',client_id=os.environ['GOOGLE_CLIENT_ID'],client_secret=os.environ['GOOGLE_CLIENT_SECRET'],server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',client_kwargs={'scope':'openid email profile'})

@contextmanager
def db():
    con=sqlite3.connect(DB_PATH,timeout=20)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con;con.commit()
    finally:con.close()

def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT, google_sub TEXT UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS profiles(user_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE, display_name TEXT NOT NULL, age INTEGER, height_cm REAL, current_weight_kg REAL, target_weight_kg REAL, fitness_goal TEXT NOT NULL, experience TEXT NOT NULL, training_days INTEGER NOT NULL, equipment TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS weight_history(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, weight_kg REAL NOT NULL CHECK(weight_kg>0), recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS workout_plans(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, title TEXT NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS workout_sessions(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, title TEXT NOT NULL, completed_on TEXT NOT NULL, notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS exercise_logs(id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES workout_sessions(id) ON DELETE CASCADE, exercise TEXT NOT NULL, sets INTEGER NOT NULL, reps INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, text TEXT NOT NULL, remind_on TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0);
        ''')
init_db()

def uid(request):return request.session.get('uid')
def csrf(request):
    if 'csrf' not in request.session:request.session['csrf']=secrets.token_urlsafe(24)
    return request.session['csrf']
def require_csrf(request,token):
    if not token or not secrets.compare_digest(str(token),str(request.session.get('csrf',''))):raise HTTPException(403,'Invalid form token. Refresh the page.')
def require_login(request):
    user=uid(request)
    if not user:raise HTTPException(401,'Please log in')
    return user
def go(path):return RedirectResponse(path,status_code=303)
def render(request,name,**kwargs):
    return tpl.TemplateResponse(request,name,dict(kwargs,csrf=csrf(request),google_ready=GOOGLE_READY,user_id=uid(request)))
def safe_error(msg):return go('/?error='+quote(msg))

@app.get('/',response_class=HTMLResponse)
def home(request:Request,error:str=''):
    if uid(request):return go('/dashboard')
    return render(request,'auth.html',error=error)

@app.post('/signup')
def signup(request:Request,email:str=Form(...),password:str=Form(...),confirm:str=Form(...),token:str=Form(...)):
    require_csrf(request,token);email=email.strip().lower()
    if len(password)<10 or password!=confirm or '@' not in email or len(email)>254:return safe_error('Use a valid email and matching password (10+ characters).')
    with db() as c:
        if c.execute('SELECT id FROM accounts WHERE email=?',(email,)).fetchone():return safe_error('This email is already registered.')
        cur=c.execute('INSERT INTO accounts(email,password_hash) VALUES (?,?)',(email,hasher.hash(password)))
        request.session.clear();request.session['uid']=cur.lastrowid
    return go('/profile')

@app.post('/login')
def login(request:Request,email:str=Form(...),password:str=Form(...),token:str=Form(...)):
    require_csrf(request,token)
    with db() as c:r=c.execute('SELECT * FROM accounts WHERE email=?',(email.strip().lower(),)).fetchone()
    if not r or not r['password_hash'] or not hasher.verify(password,r['password_hash']):return safe_error('Incorrect email or password.')
    request.session.clear();request.session['uid']=r['id']
    return go('/dashboard')

@app.post('/logout')
def logout(request:Request,token:str=Form(...)):
    require_csrf(request,token);request.session.clear();return go('/')

@app.get('/auth/google')
async def google_start(request:Request):
    if not GOOGLE_READY:raise HTTPException(503,'Google sign-in is not configured')
    return await oauth.google.authorize_redirect(request,str(request.url_for('google_callback')))

@app.get('/auth/google/callback')
async def google_callback(request:Request):
    if not GOOGLE_READY:raise HTTPException(503,'Google sign-in is not configured')
    try:
        token=await oauth.google.authorize_access_token(request)
        info=token.get('userinfo') or await oauth.google.userinfo(token=token)
        sub=info.get('sub');email=info.get('email','').lower()
        if not sub or not email or not info.get('email_verified'):raise ValueError('Unverified Google identity')
    except Exception:raise HTTPException(400,'Google sign-in failed')
    with db() as c:
        r=c.execute('SELECT id FROM accounts WHERE google_sub=?',(sub,)).fetchone()
        if not r:
            # Do not silently link a Google identity to a password account with same email.
            if c.execute('SELECT id FROM accounts WHERE email=?',(email,)).fetchone():raise HTTPException(409,'Email already registered. Log in using your password.')
            user=c.execute('INSERT INTO accounts(email,google_sub) VALUES (?,?)',(email,sub)).lastrowid
        else:user=r['id']
    request.session.clear();request.session['uid']=user
    return go('/dashboard')

@app.get('/profile',response_class=HTMLResponse)
def profile(request:Request):
    user=require_login(request)
    with db() as c:p=c.execute('SELECT * FROM profiles WHERE user_id=?',(user,)).fetchone()
    return render(request,'profile.html',p=p)

@app.post('/profile')
def save_profile(request:Request,token:str=Form(...),display_name:str=Form(...),age:int=Form(...),height_cm:float=Form(...),current_weight_kg:float=Form(...),target_weight_kg:str=Form(''),fitness_goal:str=Form(...),experience:str=Form(...),training_days:int=Form(...),equipment:str=Form(...)):
    user=require_login(request);require_csrf(request,token)
    target=None
    if target_weight_kg.strip():
        try:target=float(target_weight_kg)
        except ValueError:raise HTTPException(400,'Invalid target weight')
    if not (13<=age<=110 and 100<=height_cm<=250 and 20<=current_weight_kg<=350 and (target is None or 20<=target<=350) and 1<=training_days<=7 and 1<=len(display_name.strip())<=60):raise HTTPException(400,'Please check your profile values')
    if fitness_goal not in ('General fitness','Build strength','Improve endurance','Improve flexibility','Stay active'):raise HTTPException(400,'Invalid goal')
    if experience not in ('Beginner','Intermediate','Advanced') or equipment not in ('Home','Gym','No equipment'):raise HTTPException(400,'Invalid selection')
    with db() as c:
        prev=c.execute('SELECT current_weight_kg FROM profiles WHERE user_id=?',(user,)).fetchone()
        c.execute('''INSERT INTO profiles(user_id,display_name,age,height_cm,current_weight_kg,target_weight_kg,fitness_goal,experience,training_days,equipment) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET display_name=excluded.display_name,age=excluded.age,height_cm=excluded.height_cm,current_weight_kg=excluded.current_weight_kg,target_weight_kg=excluded.target_weight_kg,fitness_goal=excluded.fitness_goal,experience=excluded.experience,training_days=excluded.training_days,equipment=excluded.equipment,updated_at=CURRENT_TIMESTAMP''',(user,display_name.strip(),age,height_cm,current_weight_kg,target,fitness_goal,experience,training_days,equipment))
        if not prev or prev['current_weight_kg']!=current_weight_kg:c.execute('INSERT INTO weight_history(user_id,weight_kg) VALUES (?,?)',(user,current_weight_kg))
    return go('/dashboard')

def plan_for(profile):
    days=profile['training_days'];equipment=profile['equipment']
    if equipment=='Gym':base=['Bodyweight squat or leg press','Seated row','Chest press','Light mobility']
    else:base=['Chair squat','Wall push-up','Band or towel row','Gentle mobility']
    return [{'day':f'Day {i+1}','focus':['Full body','Movement and mobility','Full body','Easy activity'][i%4],'exercises':base if i%2==0 else ['Comfortable walk','Gentle stretching','Balance practice']} for i in range(days)]

@app.get('/dashboard',response_class=HTMLResponse)
def dashboard(request:Request):
    user=require_login(request)
    with db() as c:
        p=c.execute('SELECT * FROM profiles WHERE user_id=?',(user,)).fetchone()
        if not p:return go('/profile')
        history=c.execute('SELECT weight_kg,recorded_at FROM weight_history WHERE user_id=? ORDER BY id DESC LIMIT 20',(user,)).fetchall()
        sessions=c.execute('SELECT * FROM workout_sessions WHERE user_id=? ORDER BY completed_on DESC,id DESC LIMIT 30',(user,)).fetchall()
        reminders=c.execute('SELECT * FROM reminders WHERE user_id=? AND completed=0 ORDER BY remind_on LIMIT 20',(user,)).fetchall()
        plan=c.execute('SELECT * FROM workout_plans WHERE user_id=? ORDER BY id DESC LIMIT 1',(user,)).fetchone()
        total=c.execute('SELECT COUNT(*) FROM workout_sessions WHERE user_id=?',(user,)).fetchone()[0]
    today=date.today();thisweek=sum(1 for s in sessions if date.fromisoformat(s['completed_on'])>=today-timedelta(days=today.weekday()))
    achievements=[('First Workout',total>=1),('5 Workouts',total>=5),('10 Workouts',total>=10),('Weekly Consistency',thisweek>=p['training_days'])]
    first_weekday,month_days=calendar.monthrange(today.year,today.month)
    active_dates={row['completed_on'] for row in sessions}
    calendar_cells=[None]*first_weekday+[(day, date(today.year,today.month,day).isoformat() in active_dates) for day in range(1,month_days+1)]
    return render(request,'dashboard.html',calendar_cells=calendar_cells,calendar_title=today.strftime('%B %Y'),p=p,history=list(reversed(history)),sessions=sessions,reminders=reminders,plan=json.loads(plan['details_json']) if plan else None,total=total,thisweek=thisweek,achievements=achievements,today=today.isoformat())

@app.get('/progress',response_class=HTMLResponse)
def progress(request:Request):
    user=require_login(request)
    with db() as c:
        profile=c.execute('SELECT * FROM profiles WHERE user_id=?',(user,)).fetchone()
        if not profile:return go('/profile')
        weights=c.execute('SELECT weight_kg,recorded_at FROM weight_history WHERE user_id=? ORDER BY recorded_at,id',(user,)).fetchall()
        workouts=c.execute('SELECT completed_on,title,id FROM workout_sessions WHERE user_id=? ORDER BY completed_on,id',(user,)).fetchall()
        exercises=c.execute("""SELECT e.exercise, COUNT(*) AS times, SUM(e.sets) AS sets_total, SUM(e.sets*e.reps) AS reps_total
            FROM exercise_logs e JOIN workout_sessions s ON s.id=e.session_id
            WHERE s.user_id=? GROUP BY LOWER(e.exercise) ORDER BY times DESC LIMIT 8""",(user,)).fetchall()
    today=date.today()
    month_count=sum(1 for w in workouts if w['completed_on'][:7]==today.strftime('%Y-%m'))
    week_start=today-timedelta(days=today.weekday())
    week_count=sum(1 for w in workouts if week_start<=date.fromisoformat(w['completed_on'])<=today)
    target_sessions=max(1,profile['training_days'])
    adherence=round(min(100,100*week_count/target_sessions))
    weekly=[]
    for i in range(7):
        day=today-timedelta(days=6-i)
        weekly.append({'label':day.strftime('%a'),'count':sum(1 for w in workouts if w['completed_on']==day.isoformat())})
    values=[float(w['weight_kg']) for w in weights]
    low=min(values) if values else 0
    high=max(values) if values else 0
    spread=max(high-low,1)
    weight_points=[{'label':w['recorded_at'][:10],'value':w['weight_kg'],'height':round(12+76*(float(w['weight_kg'])-low)/spread)} for w in weights[-16:]]
    return render(request,'progress.html',p=profile,month_count=month_count,week_count=week_count,
        adherence=adherence,total=len(workouts),weekly=weekly,weight_points=weight_points,
        exercises=exercises,has_data=bool(workouts or weights),weight_delta=round(values[-1]-values[0],1) if len(values)>=2 else None)

@app.post('/plan')
def generate_plan(request:Request,token:str=Form(...)):
    user=require_login(request);require_csrf(request,token)
    with db() as c:
        p=c.execute('SELECT * FROM profiles WHERE user_id=?',(user,)).fetchone()
        if not p:return go('/profile')
        plan=plan_for(p)
        c.execute('INSERT INTO workout_plans(user_id,title,details_json) VALUES (?,?,?)',(user,'Starter activity plan',json.dumps(plan)))
    return go('/dashboard#plan')

@app.post('/workouts')
def add_workout(request:Request,token:str=Form(...),title:str=Form(...),completed_on:str=Form(...),exercise:str=Form(...),sets:int=Form(...),reps:int=Form(...),notes:str=Form('')):
    user=require_login(request);require_csrf(request,token)
    try:d=date.fromisoformat(completed_on)
    except ValueError:raise HTTPException(400,'Invalid date')
    if not (1<=len(title.strip())<=100 and 1<=len(exercise.strip())<=100 and 1<=sets<=20 and 1<=reps<=100 and d<=date.today()):raise HTTPException(400,'Invalid workout')
    with db() as c:
        session=c.execute('INSERT INTO workout_sessions(user_id,title,completed_on,notes) VALUES (?,?,?,?)',(user,title.strip(),completed_on,notes[:300])).lastrowid
        c.execute('INSERT INTO exercise_logs(session_id,exercise,sets,reps) VALUES (?,?,?,?)',(session,exercise.strip(),sets,reps))
    return go('/dashboard#workouts')

@app.post('/reminders')
def add_reminder(request:Request,token:str=Form(...),text:str=Form(...),remind_on:str=Form(...)):
    user=require_login(request);require_csrf(request,token)
    try:datetime.fromisoformat(remind_on)
    except ValueError:raise HTTPException(400,'Invalid reminder time')
    if not 1<=len(text.strip())<=160:raise HTTPException(400,'Invalid reminder')
    with db() as c:c.execute('INSERT INTO reminders(user_id,text,remind_on) VALUES (?,?,?)',(user,text.strip(),remind_on))
    return go('/dashboard#reminders')

@app.post('/reminders/{reminder_id}/done')
def reminder_done(request:Request,reminder_id:int,token:str=Form(...)):
    user=require_login(request);require_csrf(request,token)
    with db() as c:c.execute('UPDATE reminders SET completed=1 WHERE id=? AND user_id=?',(reminder_id,user))
    return go('/dashboard#reminders')

@app.post('/chat',response_class=HTMLResponse)
async def chat(request:Request,token:str=Form(...),question:str=Form(...)):
    user=require_login(request);require_csrf(request,token)
    q=question.strip()[:600]
    if not q:raise HTTPException(400,'Empty question')
    # Use real AI only if the server owner configured an API key. Never expose it to clients.
    if os.getenv('OPENAI_API_KEY'):
        return await ai_answer(request,user,q)
    low=q.lower()
    if any(w in low for w in ['rest','recover','tired']):reply='Rest days are part of a balanced routine. Keep activity comfortable and allow recovery.'
    elif any(w in low for w in ['plan','schedule','workout']):reply='Open My Plan and generate a starter activity schedule. Adjust it to your comfort and experience.'
    elif any(w in low for w in ['progress','track']):reply='Record completed workouts and update your profile to view your personal history.'
    elif any(w in low for w in ['food','meal','nutrition']):reply='Aim for varied meals and adequate nourishment. A photo cannot accurately measure nutrition on its own.'
    else:reply='I can help with general questions about workouts, rest, progress tracking, and using SmartFit. For individual health concerns, speak with a qualified professional.'
    return render(request,'chat.html',question=q,reply=reply)

@app.get('/meal',response_class=HTMLResponse)
def meal_page(request:Request):require_login(request);return render(request,'meal.html',result=None,error=None)

@app.post('/meal',response_class=HTMLResponse)
async def meal_scan(request:Request,token:str=Form(...),photo:UploadFile=File(...)):
    require_login(request);require_csrf(request,token)
    if photo.content_type not in ('image/jpeg','image/png','image/webp'):raise HTTPException(400,'Upload a JPEG, PNG or WebP image')
    raw=await photo.read(3_000_001)
    if len(raw)>3_000_000:raise HTTPException(413,'Image too large (max 3 MB)')
    if not os.getenv('OPENAI_API_KEY'):
        return render(request,'meal.html',result=None,error='Photo analysis requires an OPENAI_API_KEY. No estimate was generated.')
    try:
        from openai import AsyncOpenAI
        client=AsyncOpenAI(api_key=os.environ['OPENAI_API_KEY'])
        result=await client.responses.create(model=os.getenv('OPENAI_VISION_MODEL','gpt-4.1-mini'),input=[{'role':'user','content':[{'type':'input_text','text':'Describe only visually identifiable food items and possible ingredients in this image. Do not estimate exact calories, macros, portion size, or make dietary judgments. Say uncertainty clearly. Keep response under 120 words.'},{'type':'input_image','image_url':f'data:{photo.content_type};base64,{base64.b64encode(raw).decode()}'}]}],max_output_tokens=180)
        return render(request,'meal.html',result=result.output_text,error=None)
    except Exception:return render(request,'meal.html',result=None,error='Photo analysis is temporarily unavailable. Please try later.')

async def ai_answer(request:Request,user:int,question:str):
    with db() as c:
        profile=c.execute('SELECT fitness_goal,experience,training_days,equipment FROM profiles WHERE user_id=?',(user,)).fetchone()
    context=dict(profile) if profile else {}
    try:
        from openai import AsyncOpenAI
        client=AsyncOpenAI(api_key=os.environ['OPENAI_API_KEY'])
        result=await client.responses.create(model=os.getenv('OPENAI_CHAT_MODEL','gpt-4.1-mini'),instructions=('You are SmartFit Coach, a friendly fitness education assistant. Keep answers short and accessible. '
        'Do not diagnose, prescribe, suggest weight-loss diets, calorie restriction, supplements, or aggressive exercise. '
        'Respect rest, avoid appearance judgments, encourage seeking qualified help for medical concerns. '
        'User training preferences (not medical facts): '+json.dumps(context)),input=question[:600],max_output_tokens=300)
        answer=result.output_text
    except Exception:
        answer='AI service is unavailable right now. You can still use your workout tracker and progress dashboard.'
    return render(request,'chat.html',question=question[:600],reply=answer)

@app.post('/workouts/{session_id}/delete')
def delete_workout(request:Request,session_id:int,token:str=Form(...)):
    user=require_login(request);require_csrf(request,token)
    with db() as c:c.execute('DELETE FROM workout_sessions WHERE id=? AND user_id=?',(session_id,user))
    return go('/dashboard#workouts')
