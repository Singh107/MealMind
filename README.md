# MealMind

**AI-powered food intelligence for personalized recipes, grounded nutrition, pantry-aware recommendations, ingredient scanning, and meal analysis.**

🌐 **Live Demo:** https://meal-mind-sand.vercel.app

> MealMind combines generative AI with structured food data and deterministic validation so that AI can handle reasoning and interpretation without being treated as the source of truth for nutritional facts.

---

## 📸 MealMind in Action

**[SCREENSHOT 1 — HERO]**

<img width="1192" height="1030" alt="image" src="https://github.com/user-attachments/assets/9060871f-cbcd-42ec-82cf-c612aa6537fa" />


---

## What is MealMind?

MealMind is a full-stack food intelligence platform built to help users decide what to cook, understand what they're eating, and make better use of ingredients they already have.

A central design principle behind MealMind is that **generative AI and factual food data should have different responsibilities**.

Gemini handles tasks where reasoning and interpretation are useful, such as generating recipes and proposing ingredient recognition results. Structured USDA FoodData Central records are used for nutrition rather than relying on AI-generated estimates.

MealMind then independently normalizes ingredients, calculates nutrition, evaluates user constraints, and preserves uncertainty when evidence is incomplete.

---

## ✨ Features

### 🍳 Constraint-Aware Recipe Generation

Generate personalized recipes around saved preferences, dietary restrictions, ingredient exclusions, and nutrition goals.

Generated recipes are processed through MealMind's own normalization, nutrition, and constraint pipeline rather than treating the AI response as automatically correct.

**[SCREENSHOT 2 — RECIPE + NUTRITION]**

> **Add here:** Your best generated recipe screenshot. Ideally show the recipe plus some of its nutrition/constraint information.  
> If the full recipe requires scrolling, use **at most 2 screenshots** here.

---

### 🔧 Recipe Repair

When a generated recipe does not satisfy a user's requested constraints, MealMind can attempt to repair it instead of simply generating an unrelated recipe from scratch.

Repair attempts are bounded, independently recalculated, and evaluated against the original constraints before a result is selected.

This keeps the AI generation layer separate from the system responsible for determining whether a recipe actually satisfies the requested requirements.

---

### 🥫 Pantry Intelligence

MealMind allows users to maintain an account-owned pantry and uses normalized ingredient matching to understand which saved recipes can make use of ingredients they already have.

Pantry-aware ranking is deterministic and does not require another AI request just to determine ingredient overlap.

MealMind also avoids pretending to know more than the available data supports: having an ingredient in the pantry does not automatically prove that the user has enough of it to complete a recipe.

**[SCREENSHOT 3 — PANTRY]**

> **Add here:** Use one screenshot that shows your pantry populated with realistic ingredients.  
> If possible, capture pantry recommendations in the same screenshot. If that isn't possible, you can use **2 screenshots maximum** for this section.

---

### 🔄 Context-Aware Ingredient Substitutions

MealMind provides curated substitutions based on the context in which an ingredient is being used.

Users can preview substitutions before applying them, and affected nutrition and constraints can be independently recalculated rather than assuming a substitution is nutritionally equivalent.

---

### 📷 Ingredient Scanner

The Ingredient Scanner uses computer vision to propose ingredients from an uploaded image.

MealMind intentionally keeps a human in the loop. Recognition results are suggestions: users can review and edit detected ingredients before confirming what should
