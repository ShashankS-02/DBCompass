# How DBCompass recommendations work

This guide is for everyone: application owners, managers, DBAs and approvers. No technical
background is needed.

## The short version

You answer questions about your application. DBCompass compares your answers with every database
service it knows on AWS, Azure and Google Cloud. It removes the ones that cannot work, scores the
rest, prices them, and shows you the best three, with the reasons.

The same answers always give the same result. No AI decides anything: the ranking comes from fixed
rules that anyone can read. AI is only used, when switched on, to write the explanation in plain
English, and it is checked against the result before you see it. DBCompass never looks at
application code or data.

## Think of it as a hiring panel

Picture each database service as a job candidate.

| Hiring | DBCompass |
|---|---|
| The job description | Your answers: how critical the app is, how much data, how busy, what kind of data, security needs |
| Candidates | About 40 database services on AWS, Azure and Google Cloud, limited to the engines your organisation supports |
| Screening out CVs that miss a must-have | **Filters**: a service that cannot hold your kind of data, misses your availability target, cannot keep data in your region, or is being retired is removed |
| Interviewers, each scoring one topic | **Six scores**, each from 0 to 100: performance, cost, reliability, operations effort, ecosystem fit, compliance |
| How much each interviewer's vote counts | **Your priorities**: the Performance, Cost and Reliability sliders, plus fixed weights for the other three |
| References and red flags | **Rules** that add or take away points, such as "the vendor certifies this engine" (+20) or "you prefer managed services" (−10 for self-managed) |
| A shortlist of three | The **top three** options, ties broken by the lower price |

## Step by step

### 1. Your answers, and sensible defaults

You do not have to answer everything. When you skip a question, DBCompass fills it in from how
critical the application is. A business-critical application gets a high availability target, for
example. Every filled-in answer is listed on the results page under **Review your answers**, so
you can see and change what was assumed.

### 2. Filters remove what cannot work

Each removal is recorded with a reason. You can see them on the results page under
**Why not ...?** Common reasons:

- The service cannot hold your kind of data, such as relational or document data.
- Its availability promise is below your target.
- It has no region where your data must stay.
- The engine is not on the organisation's support list.
- It is a special-purpose service, such as a cache, kept for add-ons only.

### 3. Each remaining service gets six scores

| Score | What it looks at |
|---|---|
| Performance | Speed, how well it handles your write and read load |
| Cost | Its monthly price compared with the cheapest candidate (cheapest = 100) |
| Reliability | Availability promise, how little data you could lose, recovery across regions |
| Operations effort | How much work it is to run: managed or self-managed, your team's skills |
| Ecosystem fit | Change data capture, vector search, analytics feeds, licences you already own |
| Compliance | Encryption with your own keys, auditing, private network access, data masking |

### 4. Your priorities set the weights

The three sliders share 70% of the total weight between them, in proportion to where you put them.
Operations effort, ecosystem fit and compliance always count for 10% each. With every slider at
the same position, each slider is worth about 23%.

**Weighted score** = each score × its weight, added up. A weighted score of 72 means the
service meets your needs well on the things you care about most.

### 5. Rules add or remove points

Some facts matter more than a score can show, so rules adjust the total. For example:

- The vendor certifies one engine: services that run it get +20, others −15.
- Personal data needs masking: services that cannot mask data lose points.
- The application relies on engine-specific features: staying on the same engine gains points.

Every rule that fired is listed in the result, with its points.

### 6. Add-ons when one database is not enough

If you need a cache, search or analytics, DBCompass adds a matching service on the same cloud and
shows it as part of the option, such as "PostgreSQL + Redis".

### 7. Sizing and price

For each option DBCompass works out the size needed: processors, memory, storage and the
high-availability layout. It then prices that size from the cloud providers' own published price
lists, in three tiers:

- **Budget**: no spare headroom, the cheapest storage and the longest commitment you allow (up to three years).
- **Balanced**: the recommended size with normal headroom, cheapest storage and up to a one-year commitment.
- **Performance**: one size larger, one extra replica, the fastest storage, pay-as-you-go.

Commitment discounts are only used if you said you are willing to commit; otherwise every tier uses pay-as-you-go prices.

Licences for Oracle and SQL Server are added where the cloud price does not include them. Licences
you already own are not charged again, but Oracle support still is.

### 8. The ranking

Options are ranked by their final score, highest first. When two are equal, the cheaper one wins.

## For an existing database: the price difference

When you are moving an existing database, the results show what **staying on the same engine**
would cost on the same cloud. That is the cheapest service there that runs your current engine,
sized the same as the option. Only servers and licences are compared, because storage, backup and
network cost about the same either way. The card shows every line of the working.

## For a new application: the setup guide

For a new application, each option comes with basic setup steps:

- preparing the cloud account;
- creating the database;
- securing access;
- connecting the application with the right drivers;
- the schema;
- add-ons such as a cache or vector search;
- go-live checks.

## What DBCompass does not do

- It never reads application code or customer data.
- It never makes up prices, limits or service names: they come from its catalog and the
  providers' price lists, each with a source link and a date.
- It does not replace your DBA team: it gives them a well-reasoned starting point.

## Where to look on the results page

| You want to know | Look at |
|---|---|
| What I answered and what was assumed | Review your answers |
| Why this option | The "Why this" dropdown on each option |
| Why another service was not picked | Why not ...? |
| What it costs and what is in the bill | Monthly cost tiers, open a tier for the breakdown |
| What the cloud runs and what my team runs | About this service |
| How to set it up | Set up your database (new applications) |
| How to move to it | Plan migration to this option (existing applications) |
