CREATE TABLE "departments" (
"dept_no" TEXT,
  "dept_name" TEXT
);

CREATE TABLE "dept_emp" (
"emp_no" INTEGER,
  "dept_no" TEXT,
  "from_date" TEXT,
  "to_date" TEXT
);

CREATE TABLE "dept_manager" (
"emp_no" INTEGER,
  "dept_no" TEXT,
  "from_date" TEXT,
  "to_date" TEXT
);

CREATE TABLE "employees" (
"emp_no" INTEGER,
  "birth_date" TEXT,
  "first_name" TEXT,
  "last_name" TEXT,
  "gender" TEXT,
  "hire_date" TEXT
);

CREATE TABLE "salaries" (
"emp_no" INTEGER,
  "salary" INTEGER,
  "from_date" TEXT,
  "to_date" TEXT
);

CREATE TABLE "titles" (
"emp_no" INTEGER,
  "title" TEXT,
  "from_date" TEXT,
  "to_date" TEXT
);
