# Ethics 

## Product Statement

For Undergraduate SCU Students who need help with course planner, the SCU Course Planner is a web based course planner that uses their Academic Progress Report and course ratings to suggest the optional course to take. Unlike Workday or your advisor, our product automates course planning and eliminates the need to work around another person's schedule. SCU Course Planner is powered by LLM Comprehension API + Webapp front end.

## Stakeholders

SCU students are a user stakeholder for our product. These students trust our website with their Academic Progress Reports and in turn trust our recommendations. SCU faculty are a non user stakeholder for our product. For academic advisors, students might come to them with our generated schedules as a base. It's possible they will be the ones to correct mistakes we make on our website. For SCU Professors, bias in the LLM we use may encourage or discourage them causing students to over or under enroll in their course sections.

## Potential Harms

Harm 1: SCU students given poor academic planning advice. This could harm students if they pick the wrong course in the wrong order which, in the worst case, could cascade and delay their graduation.

Principle: 2. Clients

Mitigation: Our product is explicitly designed to be a starting point for students. They should not use our product as their final schedule, but instead use it to save time during the initial process of finding which course makes the most sense to take next. 



Harm 2: Some bias in either our own design or the LLM our API might cause certain professors, courses, or sections to be under or over recommended. This could harm professors as, if too many students apply and then ultimately drop out of their class, this could reflect poorly on them. Alternatively, if fewer students apply to their courses, this also would reflect poorly on the professor.

Principle: 1. Public

Mitigation: We give students multiple choices to narrow down their preferences so ideally they are matched with the most ideal professor possible. In addition, students are allowed to manually add courses to their saved schedules if they have a preference that our system didn't recommend.



Harm 3: The Academic Progress Reports that students upload are used in a way they do not consent to. For example, we could harvest the data about GPA for advertising purposes or their data could be leaked.

Principle: 2. Client

Mitigation: We stripped personally identifiable information and grades from uploaded Academic Progress Reports. In addition, we give users a clear explanation of how their data is used and an easy way to delete it permanently.


## Ethics Change

One specific decision we made based on our ethical concerns was the Data Disclosure page. Originally, we had no plans to implement this, but later on added it to the plan as a way to explicitly inform users about how their data is used. In addition, this page contains a link that deletes all user data permanently, should they choose to. This addresses Harm 3 from the previous section.
