# Build for Bharat Fellowship 2027 — Engineering take-home

## Your appointment

You have been appointed Digital Fellow in the Department of Social Welfare, Government of
Purvanchal. The **Sewa Setu Old Age Pension Portal** is live. Real citizens depend on it.
The vendor who built it is gone. The Deputy Commissioner of Sonapur district has written
recorded a short briefing for you (`dc-briefing.mp3`) — listen to it first; it is where the
citizens' complaints come from.

This is not a toy project with bugs sprinkled in. It is a small but complete inherited
system: code, a production database of ~100,000 citizens, and six months of server logs.
Your job is what a public technologist does in their first month: get it running, find out
what is actually wrong, fix what matters most, and explain your choices.

## About AI

Use whatever AI tools you like. We use them too. We are not interested in whether you wrote
every line yourself; we are interested in your judgement. Commit your agent configuration and
prompts; you will be asked what your tools got wrong.

## What you receive

A download containing: the application code, `docker-compose.yml` (app + Postgres + a fake
SMS gateway whose console is served at `/__gateway/`), `seed/seed.sql` (the citizens), the
log archive (a `.tar.gz` in `logs/` — extract it), the DC's recorded briefing
(`dc-briefing.mp3`), and this brief.
`docker compose up --build` brings up the full system with its data.

## What you must do

1. **Deploy it** on your own VM or VPS, with the database restored. No domain needed.
2. **Investigate.** The DC's briefing gives you hints on what might be going on — start there,
   then explore the code and the data.
3. **Fix what matters.** Fix as many things as you like — but your reply to the DC (recorded
   as a Loom) must name your **top 5 fixes ranked by citizen impact, with reasons**, and their
   order matters. Each fix needs a test that fails before the fix and passes after it,
   committed in that order.
4. **Do not delete or alter existing citizen records** except where a fix requires it.
   This is production data. Treat the people in it accordingly.
5. **Keep it running.** Your deployment must stay up from the moment you submit until we email
   you that the assessment is complete (up to ~30 days).

## What you submit (in the application form)

- **Deployed public URL.** (Our automated assessor completes test applications against it. The
  SMS gateway is served through your app at `/__gateway/`, so keeping your app reachable is all
  we need — there is no separate gateway URL or port to expose.)
- **Repository — give us both:**
  1. a *private* GitHub repo URL with full commit history (do not squash); invite `harshnisar`
     as a read-only collaborator (accepted automatically within minutes); **and**
  2. a **zip of your repo including the `.git` folder**, so we have your full history even if the
     invite fails. You may exclude the large files we gave you (`seed/seed.sql` and the log
     archive) — we only need your code and its history, not our data.
- **Assessor credentials:** a working admin login for our assessor. You may rebuild the
  citizen experience however you like, but **keep the admin panel functional** — it is how we
  verify your fixes. (If you rotated the admin credentials, hand over the new ones — like you
  would to an auditor.)
- **A Loom to the DC (face + screen, 3 min max):** what the evidence showed, your top 5 fixes
  ranked by citizen impact with reasons, and what you chose *not* to do and why.

## How you will be assessed

An automated probe exercises your live deployment — it may run at any time after you submit,
possibly more than once. **Everything you claim must be true at your URL.** This is a test of
engineering, not of guessing what we check, so here is exactly what the probe does:

- **Liveness** — is the app up and serving.
- **Security** — attempts the things an attacker would: reading other citizens' data,
  injection on inputs, default/leaked credentials, acting as staff without authority.
- **Data integrity** — submits an application (marked with a probe token) with an
  Indian-language name and reads it back; checks that records are stored faithfully.
- **Citizen journeys** — simulates confused and non-ideal users completing the form, and
  reads the error messages they are shown.
- **Load** — replays a month-end traffic spike and measures whether the service survives.
- **Repository** — clones your repo and checks commit history, that tests fail before a fix
  and pass after, and that the deployment matches the code.
- **The data** — logs in as citizens who existed before you arrived and checks their records
  are correct now.

We are not scoring visual polish, feature count, or how many tools you installed. More
fixes are not better fixes.

## Ground rules

- Do not attack any infrastructure other than your own deployment.
- If something outside your control breaks, tell us at the time, not afterwards. How you
  handle it is part of what we are looking at.
 
dc msg

Namaste. I am the Deputy Commissioner in charge of Seva Setu, the IT platform for old age pension. So, you are the one they have sent from Build for Bharat Fellowship? Good. Sit, sit. You will have to forgive me. I do not have a file to hand you. The vendor who built the Seva Setu portal, their contract ended, and now nobody picks up the phone. Documentation? I do not think we ever got any. So let me just tell you what's landed on my desk this past week and whatever else comes to mind.

First, an old man walked two hours from his village just to show me his acknowledgement slip, and where his name should be, in Assamese it shows four question marks. Four. He swears he typed it correctly, and I believe him because he is not the first. Others tell me their names come out cut in half, but they swear they typed it in full before submitting.

Then there's my helpdesk, overflowing. People writing in, begging us to cancel their application because they made one small mistake, realized it only after submitting, and then found there is no way to fix it, no way to go back. We delete requests, and then they submit again.

Now, before you look at the machine, you need to understand the law. There is the Right to Public Services Act. We call it RTPS. It promises every citizen a decision within a set number of days. And if we stay silent past that window, if we just sit on it, the application is deemed approved. The law says yes on our behalf, and that pension becomes the person's right. For this scheme, that window is fifteen days. For years, the overdue files used to clear themselves overnight the moment they crossed the line. Then, around Holi, it just stopped. Now files the act says should be auto-approved are sitting for months, and the appellate officer has started asking me why. I am going to be in trouble over this one.

And, uh, another thing. Every month, the two or three days before the disbursement deadline, the whole site crawls to a halt. My staff just shrug. "Server slowdown hai, sir. Kya karein?" It recovers, of course. The day after, it stops mattering. See what is going on there.

One more, and I do not know what to make of it. Meera, my assistant, she says there is a rumor going around that the moment you apply on the portal, you start getting phone calls. Salesmen. People turning up at your door trying to sell you things. Now, how on earth would that happen?

And lastly, I keep hearing the new digital form just is not friendly. Some people say they are perfectly eligible but simply cannot get through it. There are even fellows in the bazaar now who will fill it out for you for a fee because only they have figured out how it works. I would like to dismiss it as teething trouble. People always complain, but, well, who knows? We can always do better. Have a look at that too.

Here, let me give you the rules so you have them. The pension is for residents sixty years of age and above on the date they apply. One application per person. The deadline for the department is fifteen days, after which deemed approval kicks in, and an untouched file must actually be shown as approved to the citizen, and the application window closes at midnight, India Standard Time.

Come back to me once you have fixed what you can. Do not send me a report. Record me a short video, your face and your screen, and tell me the five things you fixed that matter most to these people, in order, and why. And just as important, what you saw and chose to leave alone.