# Product Design Job Finder

Finds product design jobs that match your level, location and pay, and adds them to a spreadsheet or Notion. Run it once a week. If you want, it also drafts resume bullets and a cover letter opening for each job, based only on notes you write about your own experience.

```
Status            Company   Title                            Location     Salary              Link
Ready for Review  Acme      Senior Product Designer, Growth  Remote - US  $185,000–$230,000   https://…
New               Globex    Staff Product Designer           Chicago, IL  unlisted (check …)  https://…
Applied           Initech   Design Manager, Platform         Remote - US  $200,000–$250,000   https://…
```
<sub>Your tracker: a spreadsheet (shown above) or a Notion database. Each row also says why the job matched, and holds the draft if you turned drafts on.</sub>

---

## Who it's for

Product, UX and UI designers (the defaults lean toward senior and leadership roles) who'd rather not check a dozen job sites every week. You don't need to know how to code: you paste one line into Terminal to install it, and after that you double-click files.

## What it does each week

1. Searches Indeed and the careers pages of companies you name. That works for any company that posts jobs on Greenhouse, Lever or Ashby, which most tech companies do.
2. Keeps jobs whose title, level, location, pay and posting date match your settings, and notes why each one matched.
3. Skips jobs already in your tracker.
4. Adds the rest to your tracker, with a draft for each if you turned drafts on.

## What it won't do

- It doesn't apply for you. You decide which jobs to apply to and apply on the company's site.
- It doesn't email or message anyone.
- It doesn't collect any data. There's no account and no analytics, and your settings, notes, keys and tracker stay in a folder on your computer.
- It doesn't search LinkedIn, because LinkedIn doesn't allow automated searches. Set up a saved search on LinkedIn to cover it.
- It only finds US jobs for now, and compares pay in US dollars.

## What you need

- A Mac. Windows works too, with a few manual steps (see [For tinkerers](#for-tinkerers)).
- About 10 minutes to set up.
- No money, unless you turn on drafts. Those cost about 1–2 cents per job, paid to Anthropic. The other extras (Adzuna and Notion) are free.

---

## Install

1. Open **Terminal**: press **⌘ Command + Space**, type `Terminal`, press **Return**.
2. Copy this line, paste it into Terminal, and press **Return**:

   ```
   curl -fsSL https://raw.githubusercontent.com/eriklevitch/product-design-job-finder/main/install.sh | bash
   ```

3. Answer the five questions. Press **Return** to accept the suggestion shown in [brackets].
   1. **Level:** senior individual contributor, leadership, both, or any.
   2. **Location:** your cities, and whether remote counts.
   3. **Pay:** your minimum per year.
   4. **Companies:** ones you want to work at. Type their names and it looks up their job pages.
   5. **Optional extras:** drafts, more listings, and Notion instead of a spreadsheet. Skip any of them.

4. Say **yes** to "Run your first search now?" Your tracker opens with your first jobs.

Your **job-search** folder (in your home folder) then opens in Finder. Drag it to the Finder sidebar so it's easy to find later.

<details>
<summary><b>"Python 3.10 or newer isn't on your Mac yet"</b></summary>

Go to [python.org/downloads](https://www.python.org/downloads/), click the yellow **Download** button, open the downloaded file and click **Continue** until it's done. Then paste the install line again.
</details>

## Every week

| Double-click | What it does |
|---|---|
| **Find Jobs** | Finds new jobs and adds them to your tracker. Takes 1–3 minutes. |
| **Open Tracker** | Opens your spreadsheet, or Notion in your browser. |
| **Preview Jobs** | Shows what would be added, without saving anything. Useful after you change your settings. |
| **Set Up** | Asks the setup questions again. Your current answers are the defaults. |

Then go through the new rows in your tracker. When you apply, or decide not to, update **Status**:

| Status | Meaning |
|---|---|
| **New** | Just found. |
| **Ready for Review** | Just found, and a draft is ready (if you turned drafts on). |
| **Applied** | You applied. Add the date in **Date applied**. |
| **Interview** / **Offer** / **Rejected** | How it's going. |
| **Not interested** | Hides it. Use this instead of deleting the row, so the job doesn't come back next week. |

<details>
<summary><b>Tips for the spreadsheet</b></summary>

- **Excel, Google Sheets and LibreOffice** edit `applications.csv` directly. Change Status, Date applied and Notes, then save.
- **Numbers** saves your edits as a separate `.numbers` file, and new jobs keep going to `applications.csv`. To keep everything in one place, use Excel or Google Sheets, or switch to Notion (run **Set Up** again).
- **Close the spreadsheet before you run Find Jobs**, so its new rows don't get overwritten when you save.
- Don't edit the **ID** column (the last one). It's how the tool recognizes jobs it has already added.
- Drafts are also saved as text files in the `drafts` folder, which makes them easier to copy.
</details>

<details>
<summary><b>The first time Mac says a file "can't be opened"</b></summary>

Right-click the file, choose **Open**, then click **Open** again. You only need to do this once per file.
</details>

---

## Change your search

Double-click **Set Up** and answer the questions again.

For finer changes, right-click `config.yaml` in your job-search folder, choose **Open With → TextEdit**, and change the **YOUR SEARCH** section at the top:

| Setting | What it means |
|---|---|
| `title_keywords` | A job title has to include one of these, e.g. `"product design"`, `"ux"`. |
| `seniority_keywords` | A title also has to include one of these level words, e.g. `"senior"`, `"staff"`. `[]` means any level. |
| `locations` | Places that count. Add `"remote"` to include US-remote jobs. `[]` means anywhere. |
| `search_location` | The city (or "United States") used when searching Indeed. |
| `min_salary` | Jobs whose posted pay tops out below this are skipped. Jobs that don't list pay are always kept. |
| `max_posting_age_days` | How recent a posting must be. |
| `greenhouse_companies`, `lever_companies`, `ashby_companies` | Companies checked directly. Set Up fills these in for you. |
| `tracker` | `"spreadsheet"` or `"notion"`. |

Keep the format exactly as you see it: words in `"quotes"`, lists in `[square brackets]`, separated by commas. Then double-click **Preview Jobs** to check the results.

<details>
<summary><b>Adding a company that Set Up couldn't find</b></summary>

Open the company's careers page and click any job. Look at the web address:

- `job-boards.greenhouse.io/acme/...` → add `"acme"` to `greenhouse_companies`
- `jobs.lever.co/acme/...` → add `"acme"` to `lever_companies`
- `jobs.ashbyhq.com/acme/...` → add `"acme"` to `ashby_companies`

If the address is anything else (for example, Workday or the company's own site), it can't be checked directly. Indeed will often still list their jobs.
</details>

## Optional extras

You can turn on any of these by running **Set Up** again.

<details>
<summary><b>Tailored drafts (about 1–2 cents per job)</b></summary>

For every new job, it writes three resume bullets and a cover letter opening. It uses only what you've written in `portfolio_notes.md`, so it won't invent experience you don't have.

1. Create an account at [console.anthropic.com](https://console.anthropic.com), add a few dollars of credit, then go to **API Keys → Create Key**.
2. Run **Set Up** and paste the key when asked.
3. Open `portfolio_notes.md` in your job-search folder (right-click → **Open With → TextEdit**) and replace the examples with your real experience: companies, what you led, and results with numbers. Drafts can only be as specific as these notes.

You can also change the drafts' writing rules under `writing_style` in `config.yaml`.
</details>

<details>
<summary><b>More listings from Adzuna (free)</b></summary>

Adzuna adds listings from many other job sites. Sign up at [developer.adzuna.com](https://developer.adzuna.com), copy your **App ID** and **App Key**, then run **Set Up** and paste them when asked.
</details>

<details>
<summary><b>Notion instead of a spreadsheet (free)</b></summary>

Set Up builds the database for you, with all the columns. It asks you to:

1. Go to [notion.so/profile/integrations](https://www.notion.so/profile/integrations), click **New integration**, name it "Job search", save, and copy the **Internal Integration Secret**.
2. Open (or create) the Notion page the tracker should live in. Click **•••** (top right) → **Connections** and add "Job search".
3. On that page, click **Share → Copy link**.

Paste the secret and the link when asked. Drafts appear inside each job's page.
</details>

---

## Troubleshooting

<details>
<summary><b>It found 0 matches</b></summary>

Your settings may be too narrow. Try **Set Up** again with "Any level", more cities, remote included, or a lower minimum pay. **Preview Jobs** shows how many jobs were skipped for each reason (title, level, location, pay, too old), which tells you which setting to loosen.
</details>

<details>
<summary><b>A job showed up that clearly isn't a fit</b></summary>

The **Why it matched** column shows which settings it matched. To block a word in titles, add it to `title_excludes` in `config.yaml` (in the advanced section).
</details>

<details>
<summary><b>"[jobspy] error" in the output</b></summary>

The Indeed search failed. This happens when Indeed changes its site or limits how often it can be searched. The other sources still run. To fix it, update by pasting the install line into Terminal again. Your settings, notes and tracker are kept.
</details>

<details>
<summary><b>"404 Not Found" next to a company</b></summary>

That company's name is wrong or it moved to a different careers system. Run **Set Up** and type the company name again, or see "Adding a company that Set Up couldn't find" above.
</details>

<details>
<summary><b>How do I update to the newest version?</b></summary>

Paste the install line into Terminal again. Your settings, notes, keys and tracker are kept.
</details>

<details>
<summary><b>How do I uninstall?</b></summary>

Drag the job-search folder to the Trash. Nothing else was installed.
</details>

---

## For tinkerers

<details>
<summary><b>Manual install (Mac, Linux, Windows)</b></summary>

Needs Python 3.10+.

```
git clone https://github.com/eriklevitch/product-design-job-finder.git job-search
cd job-search
python3 -m venv venv
venv/bin/pip install -r requirements.txt        # Windows: venv\Scripts\pip install -r requirements.txt
venv/bin/python engine/setup_wizard.py           # Windows: venv\Scripts\python engine\setup_wizard.py
```

Then run `venv/bin/python engine/main.py` each week (`--dry-run` to preview), and `engine/open_tracker.py` to open the tracker.
</details>

<details>
<summary><b>What's in the folder</b></summary>

| File | What it is |
|---|---|
| `config.yaml` | Your settings (made by Set Up from `config.example.yaml`). |
| `portfolio_notes.md` | Your experience, used for drafts. |
| `.env` | Your keys (hidden file). |
| `applications.csv`, `drafts/` | Your tracker and drafts. |
| `engine/` | The code. `main.py` runs the search, `sources.py` fetches and filters jobs, `draft.py` writes drafts, `tracker_csv.py` and `notion_client.py` save jobs, `check_boards.py` checks company names. |
| `tests/` | Automated checks for the filtering rules. |

Everything in the first four rows is personal and is never uploaded (see `.gitignore`).
</details>

<details>
<summary><b>Checking that the filtering is right</b></summary>

1. **Run the tests:** `venv/bin/pip install pytest` once, then `venv/bin/python -m pytest -q`. They check the title, level, location, date and pay rules against known examples. If you change a rule, add a test in `tests/test_sources.py`.
2. **Preview against real jobs:** double-click **Preview Jobs**, open 3–5 of the links and confirm the title, location, pay and date really match.
3. **Check the skip counts.** If one reason looks too high, open a few raw postings. A common cause is a location written differently than you expected, such as "NYC" instead of "New York". Add the other spelling to `locations`.
4. **Check company names:** `venv/bin/python engine/check_boards.py` checks every company in your settings and says which ones are on the wrong list or misspelled.
</details>

<details>
<summary><b>Using an AI coding assistant</b></summary>

If you use Claude Code or a similar tool, open this folder in it and ask: "Set this up for me" or "Add these companies to my search". `CLAUDE.md` tells the assistant how the project works.
</details>

## Credits

Indeed search uses [JobSpy](https://github.com/speedyapply/JobSpy). Company job lists come from the public Greenhouse, Lever and Ashby job-board APIs.

## License

MIT
