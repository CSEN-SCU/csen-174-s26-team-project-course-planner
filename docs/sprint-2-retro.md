# Sprint 2 Retrospective

## Celebrate

Ismael: Talking to the other group went well, it was nice being able to give and receive feedback. I was able to give feedback regarding responsible AI usage. I was then able to troubleshoot the data disclosure on our website to make sure anyone who accesses the website can see the disclaimer. I was also able to help get the Google sign in working on the Render site.

Jason: I shipped Google sign-in end-to-end—from the secure Streamlit flow through stateless OAuth + PKCE, to FastAPI/React with the handoff token—and then battled split-origin deployment on Render until the config matched reality. That’s real full-stack integration work under production constraints, not a demo checkbox.

Joey: I implemented both of the red team fixes. I added new pages including the Data Disclosure page, the Academic Progress Export page, Tutorial page, and Data Deletion page. Added general frontend UI improvements, such as drag and drop file uploading and the footer. Cleaned up and optimized repo, such as removing the old sign in feature.

Jiasheng:

## Red Team Response

Our team received feedback that we had problems primarily with prompt injection and data privacy concerns. We decided to deal with these issues right away since they were easy to fix and so that they wouldn’t come up later. For the prompt injection we added more system instructions stating the purpose of the application and added to treat user prompts as an unprompted source. We implemented this in the backend to ensure that a malicious user can't modify the system instructions before the website. For data privacy concerns, we added a data disclosure page that can be seen by clicking on a link at the bottom of our home page. This explicitly states how user data is processed so that users can make the most informed decisions possible.

(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/26)[https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/26]

(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/27)[https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/pull/26]

## Sprint 3 Commitments:

### Commitment 1: Add a guide for how to use the tool

For this, we want to add a guide for how to use our tool. Currently, we have a skeleton across the different pages found in the footer, but we would like this to be more cleanly integrated into the User Interface. We would like a unified guide to be accessed by clicking on a circle with a question mark in it that is by some corner of the site. 

(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/30)[https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/30]

### Commitment 2: Optimize homepage UI design 

Right now the homepage when opening the website has a lot of empty white space. We plan to make this more visually appealing by adding larger text, pictures, and some links to guides or FAQs.

(https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/31)[https://github.com/CSEN-SCU/csen-174-s26-team-project-course-planner/issues/31]

We will also try to implement features that we are missing during this week since we have a lighter work load. We plan to take advantage of this by implementing any pending Kanban boards that we have along with any new features we think of. We will try to polish everything so that the following weeks we just have to make small changes and tweaks.
