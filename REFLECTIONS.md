# Reflection

## 1. What is the single weakest part of your submission, and why did you leave it that way?

The weakest part is the lack of real-browser verification. I implemented and tested the core functionality, ran the frontend build and lint checks, and verified integration with the backend. However, I did not manually test the complete application in a browser across different screen sizes, loading states, and API failure scenarios.

I prioritized correctness of the data pipeline, API behavior, and core dashboard workflows over additional UI polish and features such as charts. This was a deliberate scope trade-off, but it leaves a gap in validating the actual user experience.

Before treating the application as production-ready, I would test the complete search, pagination, sorting, rating, and CSV export workflows in a browser, including empty results and failed requests.

## 2. Where did AI save you the most time, and where did it cost you time or nearly lead you wrong?

AI saved me the most time in implementing repetitive code and generating tests across the normalization pipeline, FastAPI endpoints, and React frontend. It also helped accelerate debugging and identify edge cases that needed explicit handling.

However, the initial title search used exact matching, so partial queries like Perf returned no results. I caught this usability issue and used AI to switch to substring matching, update the affected tests and documentation, and verify the change.

The main lesson is that passing tests do not automatically mean the behavior is right for users. AI helped me implement and test the chosen behavior, but I still needed to evaluate whether the behavior itself met the intended user experience. I treated generated code as a proposal to verify, not as a substitute for engineering judgment.

## 3. What in the data surprised you? What did you decide to not fix, and why?

The two input files contained 29 rows but only 25 unique song IDs, with four overlapping IDs. Some overlapping records had conflicting values, and the data also required handling missing values, invalid numeric representations, and inconsistent duration units.

I did not treat every duplicate title as a duplicate record. Different songs can share a title, so I retained records with distinct IDs. I also kept the original input files unchanged and generated normalized output and a separate data-quality report rather than silently rewriting the source data.

For conflicting records, I applied deterministic source precedence and used the other source as a fallback when the preferred value was missing or invalid. This made the result reproducible while keeping the normalization rules explicit.

I also made a deliberate distinction between data correction and product behavior. For example, changing title search from exact matching to substring matching was not a data-cleaning fix; it was a product behavior decision. I updated the implementation, tests, and documentation to reflect that change.

The broader lesson was that data quality work requires clear rules and traceable decisions. Not every ambiguity can be resolved automatically, and preserving information can be more appropriate than making assumptions that discard potentially valid records.

## 4. If this went to production Monday and real users hit it, what breaks first?

The biggest unverified risk is production reliability under real deployment conditions and concurrent usage. The application was built and tested as a take-home assignment, not subjected to production-like load or operational testing, so I cannot confidently claim which issue would fail first.

My first checks would be:

1. **Persistence and concurrency:** Verify SQLite behavior under concurrent rating updates, database lifecycle management, and backup and recovery.
2. **API error handling:** Exercise malformed requests, missing or invalid data, and unexpected failures to ensure the API returns predictable errors.
3. **Frontend resilience:** Check how the UI handles failed requests, empty search results, slow responses, and unsuccessful rating updates.
4. **Deployment configuration:** Validate production CORS settings, environment variables, health checks, and logging.
5. **Performance:** Measure response times and database behavior with larger datasets and concurrent users instead of assuming that passing automated tests proves scalability.

The current automated test results are useful evidence of functional correctness, but they do not establish production readiness. I would address these risks through browser-level testing, deployment validation, and targeted load and failure testing before exposing the application to real users.

