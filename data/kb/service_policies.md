# Service Policies, Disruptions and Reliability

## Disruption handling

- When a line is suspended, trains do not stop between the affected stations;
  buses are the alternative.
- Partial suspensions allow boarding outside the suspended segment.
- Delays are added to scheduled travel times; a 10 minute delay on a metro line
  affects every journey that uses that line.

## Reliability by mode

- Metro is the most reliable mode; historical punctuality is about 95 percent.
- Suburban trains are about 88 percent punctual and are more affected by fog
  and platform work.
- City buses depend on traffic; punctuality is about 80 percent and buses can
  bunch during peak hours.

## Live data policy

- Live vehicle positions, delays and cancellations come from the operator's
  real-time feed when it is reachable.
- If the live feed is unavailable, the planner must say clearly that results are
  based on the latest static schedule.
- The planner must never invent a delay, a cancellation, a bus number or a fare
  that was not provided by data.

## Replanning

- If the preferred route is disrupted, the planner offers the next best
  alternative that still satisfies the user's constraints.
- If no route satisfies every constraint, constraints are relaxed in a fixed
  order: budget, then transfers, then walking, then mode preferences, and the
  relaxation is reported to the user.
