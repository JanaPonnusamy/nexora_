# Workflow: <Workflow Name>

> Status: `Empty` · Trigger: `<event>` · Evidence: `<file:line / SP>`

## Start Screen
<Where it begins. Evidence.>

## User Action
<What the user does to trigger it. Evidence.>

## Step-by-step sequence
| # | Step (observed) | Screen/Code | DB read/write | Evidence |
|---|-----------------|-------------|---------------|----------|
| 1 | | | | |

## Database Changes
| Table | Operation (I/U/D) | Columns affected | Condition | Evidence |
|-------|-------------------|------------------|-----------|----------|

## Validation
| Rule checked | Where | Failure behaviour | Evidence |
|--------------|-------|-------------------|----------|

## Result
<End state / what the user sees. Evidence.>

## Next Screen
<Where the user lands next. Evidence.>

## Exception Handling
| Exception/Error | Detection | Message/Behaviour | Evidence |
|-----------------|-----------|-------------------|----------|

## Rollback Behaviour
<Transactions? Partial commits? What happens on failure mid-way. Evidence.>

## Linked business rules
| Rule ID (catalog) | How it applies here |
|-------------------|---------------------|
