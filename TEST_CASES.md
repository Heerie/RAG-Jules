# RAG System Test Cases

This document outlines a suite of test cases designed to evaluate the performance and robustness of the RAG system.

## Test Data

These tests assume the sample data has been created in the `/data` directory as follows:

*   `/data/project_alpha/alpha_report.pdf` (contains "Project Alpha", "budget for phase one is $1,000,000")
*   `/data/project_alpha/alpha_presentation.pptx` (contains "John Doe (Lead)")
*   `/data/project_alpha/alpha_data.csv` (contains task budgets)
*   `/data/project_beta/beta_analysis.pdf` (contains "competitor is 'MegaCorp'", "service for $40/month")
*   `/data/project_beta/beta_slides.pptx` (contains "Target Audience: Young Professionals")
*   `/data/project_beta/beta_numbers.csv` (contains monthly revenue)

## Test Suite

### Category 1: Text Retrieval

| Test ID | Query                                 | Expected Outcome                                                              |
| :------ | :------------------------------------ | :---------------------------------------------------------------------------- |
| TXT-01  | "What is Project Alpha about?"        | Should summarize the content of `alpha_report.pdf` (e.g., "AI-powered widgets"). |
| TXT-02  | "Who is the lead for Project Alpha?"  | Should identify "John Doe" from `alpha_presentation.pptx`.                    |
| TXT-03  | "What is the target audience for Project Beta?" | Should identify "Young Professionals" from `beta_slides.pptx`.                |
| TXT-04  | "What is the name of Project Beta's competitor?" | Should identify "MegaCorp" from `beta_analysis.pdf`.                         |
| TXT-05  | "What is the marketing strategy for Project Gamma?" | Should state that it cannot answer, as there is no Project Gamma.          |

### Category 2: SQL Retrieval

| Test ID | Query                                          | Expected Outcome                                                                    |
| :------ | :--------------------------------------------- | :---------------------------------------------------------------------------------- |
| SQL-01  | "What is the status of the 'User Testing' task?" | Should retrieve "not-started" from `alpha_data.csv`.                                |
| SQL-02  | "What is the total budget for all tasks in Project Alpha?" | Should calculate and return the sum of the budget column in `alpha_data.csv` (1,000,000). |
| SQL-03  | "How much revenue did Project Beta make in March?" | Should retrieve "20000" from `beta_numbers.csv`.                                    |
| SQL-04  | "What was the total revenue for Project Beta in the first quarter?" | Should calculate and return the sum of the revenue column in `beta_numbers.csv` (45000). |
| SQL-05  | "What is the employee count for Project Alpha?" | Should state that it cannot answer, as this information is not in the spreadsheets. |

### Category 3: Hybrid Retrieval

| Test ID | Query                                                                    | Expected Outcome                                                                                                        |
| :------ | :----------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------- |
| HYB-01  | "Summarize Project Alpha and what is the total budget for its tasks?"    | Should combine information from `alpha_report.pdf` (summary) and `alpha_data.csv` (sum of budget).                      |
| HYB-02  | "What is Project Beta's subscription price and who is their main competitor?" | Should combine information from `beta_analysis.pdf` ("$40/month" and "MegaCorp").                                     |
| HYB-03  | "Who is the lead of Project Alpha and what is the budget for the 'Design Widgets' task?" | Should combine information from `alpha_presentation.pptx` (John Doe) and `alpha_data.csv` (200000). |

### Category 4: Robustness and Edge Cases

| Test ID | Query                               | Expected Outcome                                                              |
| :------ | :---------------------------------- | :---------------------------------------------------------------------------- |
| ROBUST-01 | "Tell me everything about Project Alpha." | Should provide a comprehensive summary from all Project Alpha documents.      |
| ROBUST-02 | "What is the budget for Project Beta?" | Should state that the budget is not explicitly mentioned in the text documents, and the spreadsheet only contains revenue data. |
| ROBUST-03 | (Ambiguous query) "alpha data"      | Should either ask for clarification or provide a general summary of the `alpha_data.csv` file. |
