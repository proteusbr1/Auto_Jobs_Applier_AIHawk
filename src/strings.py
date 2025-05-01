

summarize_prompt_template = """
As a seasoned HR expert, your task is to identify and outline the key skills and requirements necessary for the position of this job. Use the provided job description as input to extract all relevant information. This will involve conducting a thorough analysis of the job's responsibilities and the industry standards. You should consider both the technical and soft skills needed to excel in this role. Additionally, specify any educational qualifications, certifications, or experiences that are essential. Your analysis should also reflect on the evolving nature of this role, considering future trends and how they might affect the required competencies.

Rules:
Remove boilerplate text
Include only relevant information to match the job description against the resume

# Analysis Requirements
Your analysis should include the following sections:
Technical Skills: List all the specific technical skills required for the role based on the responsibilities described in the job description.
Soft Skills: Identify the necessary soft skills, such as communication abilities, problem-solving, time management, etc.
Educational Qualifications and Certifications: Specify the essential educational qualifications and certifications for the role.
Professional Experience: Describe the relevant work experiences that are required or preferred.
Role Evolution: Analyze how the role might evolve in the future, considering industry trends and how these might influence the required skills.

# Final Result:
Your analysis should be structured in a clear and organized document with distinct sections for each of the points listed above. Each section should contain:
This comprehensive overview will serve as a guideline for the recruitment process, ensuring the identification of the most qualified candidates.

# Job Description:
```
{text}
```

---

# Job Description Summary"""

coverletter_template = """
Compose a brief and impactful cover letter based on the provided job description and resume. The letter should be no longer than three paragraphs and should be written in a professional, yet conversational tone. Avoid using any placeholders, and ensure that the letter flows naturally and is tailored to the job.

Analyze the job description to identify key qualifications and requirements. Introduce the candidate succinctly, aligning their career objectives with the role. Highlight relevant skills and experiences from the resume that directly match the job’s demands, using specific examples to illustrate these qualifications. Reference notable aspects of the company, such as its mission or values, that resonate with the candidate’s professional goals. Conclude with a strong statement of why the candidate is a good fit for the position, expressing a desire to discuss further.

Please write the cover letter in a way that directly addresses the job role and the company’s characteristics, ensuring it remains concise and engaging without unnecessary embellishments. The letter should be formatted into paragraphs and should not include a greeting or signature.

## Rules:
- Provide only the text of the cover letter.
- Do not include any introductions, explanations, or additional information.
- The letter should be formatted into paragraph.

## Job Description:
```
{job_description}
```
## My resume:
```
{resume}
```
"""

numeric_question_template = """
Read the following resume carefully and answer the specific questions regarding the candidate's experience with a number of years. Follow these strategic guidelines when responding:

1. **Related and Inferred Experience:**
   - **Similar Technologies:** If experience with a specific technology is not explicitly stated, but the candidate has experience with similar or related technologies, provide a plausible number of years reflecting this related experience. For instance, if the candidate has experience with Python and projects involving technologies similar to Java, estimate a reasonable number of years for Java.
   - **Projects and Studies:** Examine the candidate’s projects and studies to infer skills not explicitly mentioned. Complex and advanced projects often indicate deeper expertise.

2. **Indirect Experience and Academic Background:**
   - **Type of University and Studies:** Consider the type of university and course followed.
   - **Exam Grades:** Consider exam grades achieved. High grades in relevant subjects can indicate stronger proficiency and understanding.
   - **Relevant thesis:** Consider the thesis of the candidate has worked. Advanced projects suggest deeper skills.
   - **Roles and Responsibilities:** Evaluate the roles and responsibilities held to estimate experience with specific technologies or skills.


3. **Experience Estimates:**
   - **No Zero Experience:** A response of "0" is absolutely forbidden. If direct experience cannot be confirmed, provide a minimum of "2" years based on inferred or related experience.
   - **For Low Experience (up to 5 years):** Estimate experience based on inferred bacherol, skills and projects, always providing at least "2" years when relevant.
   - **For High Experience:** For high levels of experience, provide a number based on clear evidence from the resume. Avoid making inferences for high experience levels unless the evidence is strong.

4. **Rules:**
   - Answer the question directly with a number, avoiding "0" entirely.

## Example 1
```
## Curriculum

I had a degree in computer science. I have worked  years with  MQTT protocol.

## Question

How many years of experience do you have with IoT?

## Answer

4
```
## Example 1
```
## Curriculum

I had a degree in computer science. 

## Question

How many years of experience do you have with Bash?

## Answer

2
```

## Example 2
```
## Curriculum

I am a software engineer with 5 years of experience in Swift and Python. I have worked on an AI project.

## Question

How many years of experience do you have with AI?

## Answer

2
```

## Resume:
```
{resume_educations}
{resume_jobs}
{resume_projects}
```
        
## Question:
{question}

---

When responding, consider all available information, including projects, work experience, and academic background, to provide an accurate and well-reasoned answer. Make every effort to infer relevant experience and avoid defaulting to 0 if any related experience can be estimated.

"""



try_to_fix_template = """\
The objective is to fix the text of a form input on a web page.

## Rules
- Use the error to fix the original text.
- The error "Please enter a valid answer" usually means the text is too large, shorten the reply to less than a tweet.
- For errors like "Enter a whole number between 3 and 30", just need a number.

-----

## Form Question
{question}

## Input
{input} 

## Error
{error}  

## Fixed Input
"""

func_summarize_prompt_template = """
        Following are two texts, one with placeholders and one without, the second text uses information from the first text to fill the placeholders.
        
        ## Rules
        - A placeholder is a string like "[[placeholder]]". E.g. "[[company]]", "[[job_title]]", "[[years_of_experience]]"...
        - The task is to remove the placeholders from the text.
        - If there is no information to fill a placeholder, remove the placeholder, and adapt the text accordingly.
        - No placeholders should remain in the text.
        
        ## Example
        Text with placeholders: "I'm a software engineer engineer with 10 years of experience on [placeholder] and [placeholder]."
        Text without placeholders: "I'm a software engineer with 10 years of experience."
        
        -----
        
        ## Text with placeholders:
        {text_with_placeholders}
        
        ## Text without placeholders:"""

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