# Requirements Document

## Introduction

This feature adds page dwell time gating and knowledge check gating to the SCORM course engine. The "Next" button remains disabled until the learner has spent a minimum configurable time on the current page (dwell timer) and, on pages containing knowledge checks, has answered correctly. Module intro pages (first page of each module) are exempt from the dwell timer. The existing `visit_all_pages` completion strategy is preserved but now requires dwell conditions to be met before a page counts as "visited."

## Glossary

- **Course_Engine**: The single-page SCORM runtime (`course.js`) that manages lesson rendering, navigation, visited-page tracking, and SCORM communication.
- **Next_Button**: The forward navigation control (`#nav-next`) in the lesson footer that advances the learner to the subsequent page.
- **Dwell_Timer**: A per-page countdown that begins when a lesson page is rendered and elapses after the configured minimum seconds.
- **Knowledge_Check**: An interactive question element (`.knowledge-check` div) embedded in lesson content that requires the learner to select the correct answer.
- **Module_Intro_Page**: The first page of each module (`is_first_page_of_module === true`), which displays learning objectives and is exempt from the dwell timer.
- **Visited_Set**: The collection of lesson slugs that the learner has satisfied dwell and knowledge check conditions for, persisted via `cmi.suspend_data`.
- **Manifest_JSON**: The `#course-manifest` JSON blob embedded in `index.html` that provides lesson metadata to the Course_Engine at runtime.
- **Course_Config**: The `scorm` section of `course.yaml` whose values are exposed to the Course_Engine via `scormConfig` global data.

## Requirements

### Requirement 1: Dwell Timer Configuration

**User Story:** As a course author, I want to configure the minimum page dwell time in `course.yaml`, so that I can adjust pacing requirements without modifying code.

#### Acceptance Criteria

1. THE Course_Config SHALL accept a `min_page_dwell_seconds` property in the `scorm` section of `course.yaml`.
2. WHEN `min_page_dwell_seconds` is not specified in `course.yaml`, THE Course_Engine SHALL default to 5 seconds.
3. THE Manifest_JSON SHALL include the `min_page_dwell_seconds` value so the Course_Engine can read it at runtime.

### Requirement 2: Dwell Timer Behavior

**User Story:** As a course designer, I want the Next button to remain disabled until the learner has spent the minimum time on a page, so that learners engage with content before advancing.

#### Acceptance Criteria

1. WHEN a lesson page is rendered, THE Course_Engine SHALL start a dwell timer for the configured `min_page_dwell_seconds` duration.
2. WHILE the dwell timer has not elapsed, THE Next_Button SHALL be visually disabled and non-interactive.
3. WHEN the dwell timer elapses, THE Course_Engine SHALL enable the Next_Button.
4. THE Course_Engine SHALL NOT display a visible countdown or timer indicator to the learner.
5. WHEN the learner navigates away from a page before the dwell timer elapses, THE Course_Engine SHALL cancel the active dwell timer for that page.
6. WHEN the learner returns to a page whose dwell condition was previously satisfied, THE Course_Engine SHALL enable the Next_Button immediately without restarting the dwell timer.

### Requirement 3: Module Intro Page Exemption

**User Story:** As a course designer, I want module intro pages to be exempt from the dwell timer, so that learners can quickly review objectives and proceed.

#### Acceptance Criteria

1. THE Manifest_JSON SHALL include an `isFirstPageOfModule` flag for each lesson entry.
2. WHEN a page has `isFirstPageOfModule` set to true, THE Course_Engine SHALL skip the dwell timer and enable the Next_Button immediately upon rendering.
3. WHEN a page has `isFirstPageOfModule` set to true, THE Course_Engine SHALL mark the page as visited immediately upon rendering.

### Requirement 4: Knowledge Check Gating

**User Story:** As a course designer, I want the Next button to remain disabled until the learner answers a knowledge check correctly, so that comprehension is verified before progression.

#### Acceptance Criteria

1. WHEN a lesson page contains one or more Knowledge_Check elements, THE Course_Engine SHALL keep the Next_Button disabled until all Knowledge_Check elements on the page have `data-correct="true"`.
2. WHILE a Knowledge_Check has not been answered correctly, THE Course_Engine SHALL allow the learner to retry by selecting different options.
3. WHEN the learner selects an incorrect answer, THE Course_Engine SHALL display feedback, re-enable the options, and keep the Next_Button disabled.
4. WHEN the learner selects the correct answer on all Knowledge_Check elements, THE Course_Engine SHALL enable the Next_Button (subject to the dwell timer also having elapsed).
5. WHEN a page has both a dwell timer and Knowledge_Check elements, THE Course_Engine SHALL require both conditions to be satisfied before enabling the Next_Button.

### Requirement 5: Visited-Page Tracking Integration

**User Story:** As a course designer, I want pages to only count as "visited" after gating conditions are met, so that the completion strategy accurately reflects learner engagement.

#### Acceptance Criteria

1. WHEN a lesson page is rendered, THE Course_Engine SHALL NOT add the page slug to the Visited_Set until all gating conditions (dwell timer elapsed and knowledge checks answered correctly) are satisfied.
2. WHEN all gating conditions for a page are satisfied, THE Course_Engine SHALL call `markVisited` for that page's slug.
3. THE Course_Engine SHALL update the sidebar visited indicators only after a page is added to the Visited_Set.

### Requirement 6: Sidebar Navigation Freedom

**User Story:** As a learner, I want to freely navigate to any page via the sidebar, so that I can review content at my own pace.

#### Acceptance Criteria

1. THE Course_Engine SHALL allow the learner to navigate to any page via the sidebar regardless of whether previous pages have been visited.
2. WHEN the learner navigates to a new page via the sidebar, THE Course_Engine SHALL apply the dwell timer and knowledge check gating rules for that page independently.
3. WHEN the learner navigates away from a page before satisfying gating conditions, THE Course_Engine SHALL NOT add that page to the Visited_Set.

### Requirement 7: Automatic Course Completion

**User Story:** As a learner, I want the course to complete automatically once I have reached the last page with every page's gating requirements met, so that my progress is recorded without a manual step.

#### Acceptance Criteria

1. THE Course_Engine SHALL mark the course complete only when the Visited_Set contains all lesson page slugs (consistent with the existing `visit_all_pages` completion strategy). There is no manual Finish button.
2. WHEN the learner reaches the last page (`isCourseEnd === true`) and every page's dwell and knowledge check gating has been satisfied, THE Course_Engine SHALL fire completion automatically and display a completion confirmation in the lesson content.
