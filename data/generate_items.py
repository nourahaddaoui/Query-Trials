import json
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "query_trials.db"
OUTPUT_PATH = DATA_DIR / "items.jsonl"


def item(question, gold_sql, difficulty):
    return {
        "question": question,
        "gold_sql": gold_sql,
        "difficulty": difficulty,
    }


ITEMS = [
    # Development/practice items: 5 easy and 5 medium.
    item("How many employees are in the database?", "SELECT COUNT(*) AS employee_count FROM employees;", "easy"),
    item("What is the total number of departments?", "SELECT COUNT(*) AS department_count FROM departments;", "easy"),
    item("What are the first and last names of employee 10001?", "SELECT first_name, last_name FROM employees WHERE emp_no = 10001;", "easy"),
    item("What is the highest salary recorded?", "SELECT MAX(salary) AS highest_salary FROM salaries;", "easy"),
    item("How many employees are female?", "SELECT COUNT(*) AS female_employee_count FROM employees WHERE gender = 'F';", "easy"),
    item("List each department name and the number of employees assigned to it, from largest to smallest.", "SELECT d.dept_name, COUNT(de.emp_no) AS employee_count FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no GROUP BY d.dept_no, d.dept_name ORDER BY employee_count DESC;", "medium"),
    item("Which departments currently have more than 10,000 employees?", "SELECT d.dept_name, COUNT(*) AS current_employee_count FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no WHERE de.to_date = '9999-01-01' GROUP BY d.dept_no, d.dept_name HAVING COUNT(*) > 10000 ORDER BY current_employee_count DESC;", "medium"),
    item("What are the 10 lowest salaries recorded, including the employee number and salary?", "SELECT emp_no, salary FROM salaries ORDER BY salary ASC, emp_no ASC LIMIT 10;", "medium"),
    item("How many employees hold each gender, ordered by gender?", "SELECT gender, COUNT(*) AS employee_count FROM employees GROUP BY gender ORDER BY gender;", "medium"),
    item("Which five departments have the most department-manager assignment records?", "SELECT d.dept_name, COUNT(dm.emp_no) AS manager_assignment_count FROM departments AS d JOIN dept_manager AS dm ON dm.dept_no = d.dept_no GROUP BY d.dept_no, d.dept_name ORDER BY manager_assignment_count DESC, d.dept_name LIMIT 5;", "medium"),

    # Test items: 10 easy, 20 medium, and 20 hard.
    item("How many employees were hired before 1990-01-01?", "SELECT COUNT(*) AS employee_count FROM employees WHERE hire_date < '1990-01-01';", "easy"),
    item("What is the average recorded salary?", "SELECT AVG(salary) AS average_salary FROM salaries;", "easy"),
    item("What is the minimum recorded salary?", "SELECT MIN(salary) AS lowest_salary FROM salaries;", "easy"),
    item("How many salary records are still current?", "SELECT COUNT(*) AS current_salary_count FROM salaries WHERE to_date = '9999-01-01';", "easy"),
    item("How many employees have the first name Mary?", "SELECT COUNT(*) AS employee_count FROM employees WHERE first_name = 'Mary';", "easy"),
    item("How many distinct job titles are recorded?", "SELECT COUNT(DISTINCT title) AS title_count FROM titles;", "easy"),
    item("What is the total of all recorded salaries?", "SELECT SUM(salary) AS total_salary FROM salaries;", "easy"),
    item("How many department assignments are current?", "SELECT COUNT(*) AS current_assignment_count FROM dept_emp WHERE to_date = '9999-01-01';", "easy"),
    item("What are the names of departments whose number starts with d00?", "SELECT dept_name FROM departments WHERE dept_no LIKE 'd00%' ORDER BY dept_no;", "easy"),
    item("How many employees were born after 1960-01-01?", "SELECT COUNT(*) AS employee_count FROM employees WHERE birth_date > '1960-01-01';", "easy"),
    item("What is the average current salary in each department?", "SELECT d.dept_name, AVG(s.salary) AS average_current_salary FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no JOIN salaries AS s ON s.emp_no = de.emp_no AND s.to_date = '9999-01-01' WHERE de.to_date = '9999-01-01' GROUP BY d.dept_no, d.dept_name ORDER BY average_current_salary DESC;", "medium"),
    item("List the 10 departments with the fewest current employees.", "SELECT d.dept_name, COUNT(de.emp_no) AS current_employee_count FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no AND de.to_date = '9999-01-01' GROUP BY d.dept_no, d.dept_name ORDER BY current_employee_count ASC, d.dept_name LIMIT 10;", "medium"),
    item("Which job titles have more than 50,000 records?", "SELECT title, COUNT(*) AS title_record_count FROM titles GROUP BY title HAVING COUNT(*) > 50000 ORDER BY title_record_count DESC, title;", "medium"),
    item("What is the highest salary for each employee among employees numbered below 10010?", "SELECT emp_no, MAX(salary) AS highest_salary FROM salaries WHERE emp_no < 10010 GROUP BY emp_no ORDER BY emp_no;", "medium"),
    item("Which departments have at least two manager assignment records?", "SELECT d.dept_name, COUNT(*) AS manager_assignment_count FROM departments AS d JOIN dept_manager AS dm ON dm.dept_no = d.dept_no GROUP BY d.dept_no, d.dept_name HAVING COUNT(*) >= 2 ORDER BY d.dept_name;", "medium"),
    item("List the five most common first names among employees.", "SELECT first_name, COUNT(*) AS employee_count FROM employees GROUP BY first_name ORDER BY employee_count DESC, first_name LIMIT 5;", "medium"),
    item("What are the current job titles held by employee 10001?", "SELECT title FROM titles WHERE emp_no = 10001 AND to_date = '9999-01-01' ORDER BY from_date;", "medium"),
    item("Which employees have had more than three salary records?", "SELECT emp_no, COUNT(*) AS salary_record_count FROM salaries GROUP BY emp_no HAVING COUNT(*) > 3 ORDER BY salary_record_count DESC, emp_no;", "medium"),
    item("What is the total current payroll for each department?", "SELECT d.dept_name, SUM(s.salary) AS current_payroll FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no AND de.to_date = '9999-01-01' JOIN salaries AS s ON s.emp_no = de.emp_no AND s.to_date = '9999-01-01' GROUP BY d.dept_no, d.dept_name ORDER BY current_payroll DESC;", "medium"),
    item("Which departments currently have a manager?", "SELECT d.dept_name, dm.emp_no AS manager_emp_no FROM departments AS d JOIN dept_manager AS dm ON dm.dept_no = d.dept_no WHERE dm.to_date = '9999-01-01' ORDER BY d.dept_no;", "medium"),
    item("List employees hired in the 1980s who are currently assigned to a department.", "SELECT DISTINCT e.emp_no, e.first_name, e.last_name FROM employees AS e JOIN dept_emp AS de ON de.emp_no = e.emp_no WHERE e.hire_date >= '1980-01-01' AND e.hire_date < '1990-01-01' AND de.to_date = '9999-01-01' ORDER BY e.emp_no;", "medium"),
    item("What is the average salary by gender for employees with a current salary?", "SELECT e.gender, AVG(s.salary) AS average_current_salary FROM employees AS e JOIN salaries AS s ON s.emp_no = e.emp_no WHERE s.to_date = '9999-01-01' GROUP BY e.gender ORDER BY e.gender;", "medium"),
    item("Which current departments have an average current salary above 60,000?", "SELECT d.dept_name, AVG(s.salary) AS average_current_salary FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no AND de.to_date = '9999-01-01' JOIN salaries AS s ON s.emp_no = de.emp_no AND s.to_date = '9999-01-01' GROUP BY d.dept_no, d.dept_name HAVING AVG(s.salary) > 60000 ORDER BY average_current_salary DESC;", "medium"),
    item("List the 10 employees with the most title records.", "SELECT e.emp_no, e.first_name, e.last_name, COUNT(t.title) AS title_record_count FROM employees AS e JOIN titles AS t ON t.emp_no = e.emp_no GROUP BY e.emp_no, e.first_name, e.last_name ORDER BY title_record_count DESC, e.emp_no LIMIT 10;", "medium"),
    item("Which current department managers are also current employees in their managed department?", "SELECT dm.emp_no, d.dept_name FROM dept_manager AS dm JOIN departments AS d ON d.dept_no = dm.dept_no JOIN dept_emp AS de ON de.emp_no = dm.emp_no AND de.dept_no = dm.dept_no WHERE dm.to_date = '9999-01-01' AND de.to_date = '9999-01-01' ORDER BY dm.emp_no;", "medium"),
    item("For each department, what is the earliest employee assignment start date?", "SELECT d.dept_name, MIN(de.from_date) AS earliest_assignment_date FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no GROUP BY d.dept_no, d.dept_name ORDER BY earliest_assignment_date, d.dept_name;", "medium"),
    item("Which employees currently have a title containing the word Engineer?", "SELECT DISTINCT e.emp_no, e.first_name, e.last_name FROM employees AS e JOIN titles AS t ON t.emp_no = e.emp_no WHERE t.to_date = '9999-01-01' AND t.title LIKE '%Engineer%' ORDER BY e.emp_no;", "medium"),
    item("What is the current salary range in each department?", "SELECT d.dept_name, MIN(s.salary) AS lowest_current_salary, MAX(s.salary) AS highest_current_salary FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no AND de.to_date = '9999-01-01' JOIN salaries AS s ON s.emp_no = de.emp_no AND s.to_date = '9999-01-01' GROUP BY d.dept_no, d.dept_name ORDER BY d.dept_name;", "medium"),
    item("Which departments have more than 5,000 current employees and a current manager?", "SELECT d.dept_name, COUNT(DISTINCT de.emp_no) AS current_employee_count FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no AND de.to_date = '9999-01-01' JOIN dept_manager AS dm ON dm.dept_no = d.dept_no AND dm.to_date = '9999-01-01' GROUP BY d.dept_no, d.dept_name HAVING COUNT(DISTINCT de.emp_no) > 5000 ORDER BY current_employee_count DESC;", "medium"),
    item("Which employees have both a current title and a current salary above 100,000?", "SELECT DISTINCT e.emp_no, e.first_name, e.last_name FROM employees AS e JOIN titles AS t ON t.emp_no = e.emp_no AND t.to_date = '9999-01-01' JOIN salaries AS s ON s.emp_no = e.emp_no AND s.to_date = '9999-01-01' WHERE s.salary > 100000 ORDER BY e.emp_no;", "hard"),
    item("Which departments have a current payroll greater than the average current department payroll?", "SELECT d.dept_name, SUM(s.salary) AS current_payroll FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no AND de.to_date = '9999-01-01' JOIN salaries AS s ON s.emp_no = de.emp_no AND s.to_date = '9999-01-01' GROUP BY d.dept_no, d.dept_name HAVING SUM(s.salary) > (SELECT AVG(department_payroll) FROM (SELECT SUM(s2.salary) AS department_payroll FROM dept_emp AS de2 JOIN salaries AS s2 ON s2.emp_no = de2.emp_no AND s2.to_date = '9999-01-01' WHERE de2.to_date = '9999-01-01' GROUP BY de2.dept_no) AS payrolls) ORDER BY current_payroll DESC;", "hard"),
    item("Which employees have a current salary higher than the average current salary?", "SELECT e.emp_no, e.first_name, e.last_name, s.salary FROM employees AS e JOIN salaries AS s ON s.emp_no = e.emp_no WHERE s.to_date = '9999-01-01' AND s.salary > (SELECT AVG(s2.salary) FROM salaries AS s2 WHERE s2.to_date = '9999-01-01') ORDER BY s.salary DESC, e.emp_no;", "hard"),
    item("What is the highest current salary in each department, and which employee earns it?", "SELECT d.dept_name, e.emp_no, e.first_name, e.last_name, s.salary FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no AND de.to_date = '9999-01-01' JOIN employees AS e ON e.emp_no = de.emp_no JOIN salaries AS s ON s.emp_no = e.emp_no AND s.to_date = '9999-01-01' WHERE s.salary = (SELECT MAX(s2.salary) FROM dept_emp AS de2 JOIN salaries AS s2 ON s2.emp_no = de2.emp_no AND s2.to_date = '9999-01-01' WHERE de2.dept_no = d.dept_no AND de2.to_date = '9999-01-01') ORDER BY d.dept_no, e.emp_no;", "hard"),
    item("Which employees have received a salary increase in every consecutive salary record?", "SELECT s.emp_no FROM salaries AS s JOIN salaries AS previous_s ON previous_s.emp_no = s.emp_no AND previous_s.to_date = s.from_date WHERE s.salary > previous_s.salary GROUP BY s.emp_no HAVING COUNT(*) = (SELECT COUNT(*) FROM salaries AS all_s WHERE all_s.emp_no = s.emp_no) - 1 ORDER BY s.emp_no;", "hard"),
    item("For each employee, what is the percentage increase from their first to their latest recorded salary?", "SELECT emp_no, ROUND(100.0 * (latest_salary - first_salary) / first_salary, 2) AS percentage_increase FROM (SELECT emp_no, FIRST_VALUE(salary) OVER (PARTITION BY emp_no ORDER BY from_date) AS first_salary, LAST_VALUE(salary) OVER (PARTITION BY emp_no ORDER BY from_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS latest_salary FROM salaries) GROUP BY emp_no, first_salary, latest_salary ORDER BY percentage_increase DESC, emp_no;", "hard"),
    item("Which departments have more current employees than the company-wide average current department size?", "SELECT d.dept_name, COUNT(*) AS current_employee_count FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no WHERE de.to_date = '9999-01-01' GROUP BY d.dept_no, d.dept_name HAVING COUNT(*) > (SELECT AVG(department_size) FROM (SELECT COUNT(*) AS department_size FROM dept_emp WHERE to_date = '9999-01-01' GROUP BY dept_no) AS sizes) ORDER BY current_employee_count DESC;", "hard"),
    item("Which employees have held more distinct titles than the average employee?", "SELECT e.emp_no, e.first_name, e.last_name, COUNT(DISTINCT t.title) AS distinct_title_count FROM employees AS e JOIN titles AS t ON t.emp_no = e.emp_no GROUP BY e.emp_no, e.first_name, e.last_name HAVING COUNT(DISTINCT t.title) > (SELECT AVG(title_count) FROM (SELECT COUNT(DISTINCT title) AS title_count FROM titles GROUP BY emp_no) AS title_counts) ORDER BY distinct_title_count DESC, e.emp_no;", "hard"),
    item("What is the average number of salary records for employees in each department?", "SELECT d.dept_name, AVG(employee_salary_records) AS average_salary_records FROM departments AS d JOIN (SELECT de.dept_no, de.emp_no, COUNT(s.emp_no) AS employee_salary_records FROM dept_emp AS de JOIN salaries AS s ON s.emp_no = de.emp_no GROUP BY de.dept_no, de.emp_no) AS records ON records.dept_no = d.dept_no GROUP BY d.dept_no, d.dept_name ORDER BY average_salary_records DESC;", "hard"),
    item("Which current department has the largest difference between its highest and lowest current salaries?", "SELECT d.dept_name, MAX(s.salary) - MIN(s.salary) AS salary_range FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no AND de.to_date = '9999-01-01' JOIN salaries AS s ON s.emp_no = de.emp_no AND s.to_date = '9999-01-01' GROUP BY d.dept_no, d.dept_name ORDER BY salary_range DESC, d.dept_name LIMIT 1;", "hard"),
    item("Which employees have a current title but no current department assignment?", "SELECT e.emp_no, e.first_name, e.last_name FROM employees AS e WHERE EXISTS (SELECT 1 FROM titles AS t WHERE t.emp_no = e.emp_no AND t.to_date = '9999-01-01') AND NOT EXISTS (SELECT 1 FROM dept_emp AS de WHERE de.emp_no = e.emp_no AND de.to_date = '9999-01-01') ORDER BY e.emp_no;", "hard"),
    item("Which departments have no current manager?", "SELECT d.dept_name FROM departments AS d WHERE NOT EXISTS (SELECT 1 FROM dept_manager AS dm WHERE dm.dept_no = d.dept_no AND dm.to_date = '9999-01-01') ORDER BY d.dept_no;", "hard"),
    item("For each year from 1985 through 1989, how many employees were hired?", "SELECT strftime('%Y', hire_date) AS hire_year, COUNT(*) AS employee_count FROM employees WHERE hire_date >= '1985-01-01' AND hire_date < '1990-01-01' GROUP BY strftime('%Y', hire_date) ORDER BY hire_year;", "hard"),
    item("Which departments had an employee assignment begin in every year from 1985 through 1989?", "SELECT d.dept_name FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no WHERE CAST(strftime('%Y', de.from_date) AS INTEGER) BETWEEN 1985 AND 1989 GROUP BY d.dept_no, d.dept_name HAVING COUNT(DISTINCT strftime('%Y', de.from_date)) = 5 ORDER BY d.dept_name;", "hard"),
    item("Which employees changed titles at least twice, based on adjacent title dates?", "SELECT e.emp_no, e.first_name, e.last_name, COUNT(*) AS title_changes FROM employees AS e JOIN titles AS t ON t.emp_no = e.emp_no JOIN titles AS next_t ON next_t.emp_no = t.emp_no AND next_t.from_date = t.to_date GROUP BY e.emp_no, e.first_name, e.last_name HAVING COUNT(*) >= 2 ORDER BY title_changes DESC, e.emp_no;", "hard"),
    item("What is the median current salary using the two middle salary positions when the count is even?", "SELECT AVG(salary) AS median_current_salary FROM (SELECT salary FROM salaries WHERE to_date = '9999-01-01' ORDER BY salary LIMIT 2 - (SELECT COUNT(*) FROM salaries WHERE to_date = '9999-01-01') % 2 OFFSET (SELECT (COUNT(*) - 1) / 2 FROM salaries WHERE to_date = '9999-01-01'));", "hard"),
    item("Which employees have a current salary that is higher than every current salary of employee 10001?", "SELECT e.emp_no, e.first_name, e.last_name, s.salary FROM employees AS e JOIN salaries AS s ON s.emp_no = e.emp_no WHERE s.to_date = '9999-01-01' AND s.salary > (SELECT MAX(s2.salary) FROM salaries AS s2 WHERE s2.emp_no = 10001 AND s2.to_date = '9999-01-01') ORDER BY s.salary DESC, e.emp_no;", "hard"),
    item("For each department, what percentage of its current employees are female?", "SELECT d.dept_name, ROUND(100.0 * SUM(CASE WHEN e.gender = 'F' THEN 1 ELSE 0 END) / COUNT(*), 2) AS female_percentage FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no AND de.to_date = '9999-01-01' JOIN employees AS e ON e.emp_no = de.emp_no GROUP BY d.dept_no, d.dept_name ORDER BY female_percentage DESC, d.dept_name;", "hard"),
    item("Which current department managers earn more than the average current salary of their department?", "SELECT d.dept_name, e.emp_no, e.first_name, e.last_name, s.salary FROM dept_manager AS dm JOIN departments AS d ON d.dept_no = dm.dept_no JOIN employees AS e ON e.emp_no = dm.emp_no JOIN salaries AS s ON s.emp_no = dm.emp_no AND s.to_date = '9999-01-01' WHERE dm.to_date = '9999-01-01' AND s.salary > (SELECT AVG(s2.salary) FROM dept_emp AS de2 JOIN salaries AS s2 ON s2.emp_no = de2.emp_no AND s2.to_date = '9999-01-01' WHERE de2.dept_no = dm.dept_no AND de2.to_date = '9999-01-01') ORDER BY d.dept_no;", "hard"),
    item("Which employees have held the same title for more than 5 years based on title dates?", "SELECT e.emp_no, e.first_name, e.last_name, t.title FROM employees AS e JOIN titles AS t ON t.emp_no = e.emp_no WHERE (julianday(t.to_date) - julianday(t.from_date)) > 1825 ORDER BY e.emp_no, t.from_date;", "medium"),
    item("Which departments have more current employees than all departments whose number starts with d00?", "SELECT d.dept_name, COUNT(*) AS current_employee_count FROM departments AS d JOIN dept_emp AS de ON de.dept_no = d.dept_no AND de.to_date = '9999-01-01' GROUP BY d.dept_no, d.dept_name HAVING COUNT(*) > (SELECT MAX(department_size) FROM (SELECT COUNT(*) AS department_size FROM dept_emp AS de2 JOIN departments AS d2 ON d2.dept_no = de2.dept_no WHERE de2.to_date = '9999-01-01' AND d2.dept_no LIKE 'd00%' GROUP BY d2.dept_no) AS reference_sizes) ORDER BY current_employee_count DESC;", "hard"),
]


def validate_items(items):
    assert len(items) == 60, f"Expected 60 items, got {len(items)}"
    assert sum(entry["difficulty"] == "easy" for entry in items) == 15
    assert sum(entry["difficulty"] == "medium" for entry in items) == 25
    assert sum(entry["difficulty"] == "hard" for entry in items) == 20
    assert len({entry["question"] for entry in items}) == 60
    assert all(set(entry) == {"question", "gold_sql", "difficulty"} for entry in items)

    if DATABASE_PATH.exists():
        with sqlite3.connect(DATABASE_PATH) as connection:
            for entry in items:
                connection.execute("EXPLAIN " + entry["gold_sql"])


def write_items():
    validate_items(ITEMS)
    DATA_DIR.mkdir(exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as output_file:
        for entry in ITEMS:
            output_file.write(json.dumps({key: entry[key] for key in ("question", "gold_sql")}, ensure_ascii=True) + "\n")

    print(f"Wrote {len(ITEMS)} items to {OUTPUT_PATH}")
    print("Development items: lines 1-10; test items: lines 11-60")


if __name__ == "__main__":
    write_items()