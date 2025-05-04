# src/llm/prompts.py
evaluate_job_template = """
You are a Human Resources expert specializing in evaluating job applications for the {location} job market. Your task is to assess the compatibility between the following job description and a provided resume.
Return only a score from 0 to 10 representing the candidate's likelihood of securing the position, with 0 being the lowest probability and 10 being the highest.
The assessment should consider HR-specific criteria for the {location} job market, including skills, experience, education, and any other relevant criteria mentioned in the job description.

Job Title:
({job_title})

Job Salary:
({job_salary})

Job Description:
({job_description})

My Resume:
({resume_summary})

Score (0 to 10):
"""

estimate_salary_template = """
You are a Human Resources expert specializing in evaluating job applications for the {location} job market.
Given the job description and the candidate's resume below, estimate the annual salary in US dollars that the employer is likely to offer to this candidate.
Provide your answer as a single number, representing the annual salary in US dollars, without any additional text, units, currency symbols, or ranges.
If the salary is given as a range, return only the highest value in the range. Do not include any explanations.

Job Title:
({job_title})

Job Salary:
({job_salary})

Job Description:
({job_description})

My Resume:
({resume_summary})

Estimated annual Salary (in US dollars):
"""

simple_question_template = """
You are an AI assistant specializing in human resources and knowledgeable about the {location} job market. Your role is to help me secure a job by answering questions related to my resume and a job description. Follow these rules:
- Answer questions directly.
- Keep the answer under {limit_caractere} characters.
- If not sure, provide an approximate answer.

Job Title:
({job_title})

Job Salary:
({job_salary})

Job Description:
({job_description})

Resume:
({resume})

Question:
({question})

Answer:
"""

numeric_question_template = """
You are an expert in extracting information from resume data.
Given the following resume summary and a question, please determine the most appropriate numeric answer.

Resume Summary:
{resume_summary}

Question: {question}

Return only a single number as your answer. No explanation is needed.
"""

extract_keywords_template = """
Extract the most important keywords from the following job description that HR systems
or automated bots would use to evaluate and rank resumes. Return the keywords as a JSON list.
Return the JSON list and nothing else.

Job Description:
({job_description})

Keywords:
"""

tailored_summary_template = """
Using the following resume, resume summary, and keywords extracted from a job description,
create a concise and professional tailored resume summary that highlights the most relevant skills and experiences
to increase the likelihood of passing through HR evaluation systems. Ensure the summary is truthful
and only includes information provided. Incorporate the keywords appropriately without fabricating or exaggerating any information.

Old Resume Summary:
({resume_summary})

Resume:
({resume})

Keywords:
({keywords_str})

Please provide the tailored resume summary below without any headings or labels:
"""

cover_letter_template = """
Using the following job description, resume, and keywords, compose a concise and professional cover letter that emphasizes the most relevant skills and experiences.
Ensure the cover letter is truthful and only includes information provided. Incorporate the keywords appropriately without fabricating or exaggerating any information.
The cover letter should not exceed 300 words and should be written in paragraph form.

Job Description:
({job_description})

Resume:
({resume})

Keywords:
({keywords_str})

Please provide the Cover Letter: below without any headings or labels:
"""

resume_or_cover_template = """
Given the following phrase, respond with only 'resume' if the phrase is about a resume, or 'cover' if it's about a cover letter.
If the phrase contains only one word 'upload', consider it as 'cover'.
If the phrase contains 'upload resume', consider it as 'resume'.
Do not provide any additional information or explanations.

phrase: {phrase}
"""

options_template = """The following is a resume and an answered question about the resume, the answer is one of the options.

## Rules
- Never choose the default/placeholder option, examples are: 'Select an option', 'None', 'Choose from the options below', etc.
- The answer must be one of the options.
- The answer must exclusively contain one of the options.

## Example
My resume: I'm a software engineer with 10 years of experience on swift, python, C, C++.
Question: How many years of experience do you have on python?
Options: [1-2, 3-5, 6-10, 10+]
10+

-----

## My resume:
```
{resume}
```

## Question:
{question}

## Options:
{options}

## """

date_question_template = """
You are an AI assistant helping to provide appropriate dates in response to questions during a job application process.

- Read the question carefully.
- Today's date is {today_date}.
- Determine the most suitable date to answer the question based on common professional scenarios.
- The date should be formatted as YYYY-MM-DD.

Examples:

- If the question is about the earliest start date, and you are available in two weeks, provide a date two weeks from today.
- If the question is about availability, and you are available immediately, provide today's date.
- If the question is about notice period, and you have a standard two-week notice period, provide a date two weeks from today.

Do not include any additional text or explanation—only provide the date in YYYY-MM-DD format.

Question: "{question}"

Date:
"""