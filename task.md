# Task: Battle Mode Free Movement & Design Renovation

## Planning

- [x] Research Current Implementation
- [x] Define Implementation Plan (Free Movement, Design, Backgrounds)
- [x] Review & Approval

## Backend Implementation

- [x] Support Float Coordinates (`common_manager.py`)
- [x] Implement Background Image Settings (`common_manager.py`, `common_routes.py`)

## Frontend Implementation

- [x] Remove Grid Snapping (`tab_visual_battle.js`: ondrop)
- [x] Implement Rounded Square Token Design (`tab_visual_battle.js`: createMapToken)
- [x] Implement Background Settings UI (`tab_visual_battle.js`)
- [x] Update VisualMap to render background (`tab_visual_battle.js`)

## Refinement (Feedback 1)

- [x] Fix Dragging "Snap" / "Sticky" Feeling (Use custom MouseEvents)
- [x] Improve Token Visuals (Name truncated -> Overlay, HP/MP layout)

## Refinement (Feedback 2)

- [x] Move Name Label Outside (Below Token)
- [x] Fix Sticky Movement (Precision Rounding & Drag Threshold)
- [x] Add Attack Target Highlight (`enterAttackTargetingMode`)
- [x] Prevent "Click" after "Drag" (`window._dragBlockClick`)

## Refinement (Feedback 3)

- [x] Fix Click Block Logic (Increase Threshold to 5px, Disable Transition)
- [x] Change Target Highlight to Gold
- [x] Remove CSS Transition interference during drag

## Fixes & Polish

- [x] Fix Frontend SyntaxError (Duplicate declaration & Incorrect grouping)
- [x] Fix Backend Coordinate Rounding (int -> float) to Stop Teleporting

## Verification

- [x] Verify Free Movement (Drag & Drop)
- [x] Verify Token Design (Status Bars, Badges, Name Label)
- [x] Verify Background Settings (Set & Persist)
- [x] Verify Target Mode Visuals and Click Logic
