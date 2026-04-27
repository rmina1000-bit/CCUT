// testPbeWindow.ts
import { buildPbeWindow } from "./pbeWindow";
import { Fragment } from "@/data/fragmentData";

function makeFrag(id: string, source: string, start: number, end: number): Fragment {
    return {
        fragment_id: id,
        fragment_uid: id,
        root_fragment_uid: id,
        display_id: id,
        selection_state: "S",
        status: "committed",
        source_video: source,
        start_frame: start,
        end_frame: end,
        duration: end - start,
        thumbnail: { thumbnail_url: "" },
        intelligence: {},
    } as unknown as Fragment; // cast for brevity
}

// Same-source example: L and R from same source with surrounding fragments
const sameSourceFragments = [
    makeFrag("f0", "A", 0, 10), // prev(L)
    makeFrag("f1", "A", 10, 20), // L
    makeFrag("f2", "A", 20, 30), // R
    makeFrag("f3", "A", 30, 40), // next(R)
];
console.log("--- Same Source ---");
console.log(buildPbeWindow({ leftFragment: sameSourceFragments[1], rightFragment: sameSourceFragments[2], sourceFragments: sameSourceFragments }));

// Cross-source example: L from A, R from B
const crossSourceFragments = [
    makeFrag("f1", "A", 10, 20), // L
    makeFrag("f2", "A", 20, 30), // next(L)
    makeFrag("f3", "B", 0, 10), // prev(R)
    makeFrag("f4", "B", 10, 20), // R
];
console.log("--- Cross Source ---");
console.log(buildPbeWindow({ leftFragment: crossSourceFragments[0], rightFragment: crossSourceFragments[3], sourceFragments: crossSourceFragments }));

// Single left edge
const singleLeftFragments = [
    makeFrag("f0", "A", 0, 10), // prev(L)
    makeFrag("f1", "A", 10, 20), // L
];
console.log("--- Single Left ---");
console.log(buildPbeWindow({ leftFragment: singleLeftFragments[1], rightFragment: null, sourceFragments: singleLeftFragments }));

// Single right edge
const singleRightFragments = [
    makeFrag("f0", "B", 0, 10), // R
    makeFrag("f1", "B", 10, 20), // next(R)
];
console.log("--- Single Right ---");
console.log(buildPbeWindow({ leftFragment: null, rightFragment: singleRightFragments[0], sourceFragments: singleRightFragments }));
