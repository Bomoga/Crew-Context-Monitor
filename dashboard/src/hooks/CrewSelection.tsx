import { createContext, useContext, useState, type ReactNode } from "react";

interface Selection {
  /** The crew member chosen in the crew strip, or null to follow the first one. */
  selected: string | null;
  select: (id: string) => void;
}

const CrewSelectionContext = createContext<Selection>({ selected: null, select: () => {} });

/** Which crew member the timeline shows; shared by the crew strip and the charts. */
export function CrewSelectionProvider({ children }: { children: ReactNode }) {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <CrewSelectionContext.Provider value={{ selected, select: setSelected }}>
      {children}
    </CrewSelectionContext.Provider>
  );
}

/** The selected crew id if it is one of `ids`, else the first of `ids`. */
export function useSelectedCrew(ids: readonly string[]): [string | null, (id: string) => void] {
  const { selected, select } = useContext(CrewSelectionContext);
  const effective = selected !== null && ids.includes(selected) ? selected : (ids[0] ?? null);
  return [effective, select];
}
