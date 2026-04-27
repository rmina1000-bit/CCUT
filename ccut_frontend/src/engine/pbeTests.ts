import { Fragment, applyPairBoundary, processCentralGap, InvariantValidator, getPairState } from "./pbeCore";

/**
 * 9. 테스트 - QA-01 ~ QA-05 구현
 */

const QA01_SN_SameSource = () => {
    console.log("--- QA-01 ---");
    const A1: Fragment = { fragment_id: "A1", source_video: "V1", start_frame: 0, end_frame: 10, duration: 10, selection_state: "S" };
    const A2: Fragment = { fragment_id: "A2", source_video: "V1", start_frame: 10, end_frame: 20, duration: 10, selection_state: "N" };

    // 조작: x = 15 (B잠식 5프레임)
    const result = applyPairBoundary(A1, A2, 15);

    // 기대 결과: L(A1, 10f), R_sub(A2_L, 5f), R_rem(A2_rem, 5f)
    // Our applyPairBoundary returns fA_sel, fB_sel, fB_rem for (S,N) x > nA
    console.log("QA-01 Results:", result);

    const allFrags = [result.fA_sel!, result.fB_sel!, result.fB_rem!];
    const { valid, errors } = InvariantValidator.validate(allFrags);

    const pass = valid && result.fB_sel?.duration === 5 && result.fB_sel?.derivedFrom === "A2";
    console.log(`QA-01 PASS: ${pass}`, errors);
    return pass;
};

const QA02_CrossSource_Remnant = () => {
    console.log("--- QA-02 ---");
    const L: Fragment = { fragment_id: "L", source_video: "V1", start_frame: 0, end_frame: 10, duration: 10, selection_state: "S" };
    const gap: Fragment = { fragment_id: "1-2", source_video: "V1", start_frame: 10, end_frame: 20, duration: 10, selection_state: "N" };
    const R: Fragment = { fragment_id: "R", source_video: "V2", start_frame: 0, end_frame: 10, duration: 10, selection_state: "S" };

    // 조작: a=3, b=3 잠식
    const result = processCentralGap(gap, 3, 3);

    // 결과: L(10f), 1-2_L(3f), 1-2_M(4f), 1-2_R(3f), R(10f)
    console.log("QA-02 Results:", result);

    const pass = result.mid_rem?.duration === 4 && result.left_sub?.duration === 3 && result.right_sub?.duration === 3;
    console.log(`QA-02 PASS: ${pass}`);
    return pass;
};

const QA03_CrossSource_Disappearance = () => {
    console.log("--- QA-03 ---");
    const gap: Fragment = { fragment_id: "1-2", source_video: "V1", start_frame: 10, end_frame: 20, duration: 10, selection_state: "N" };

    // 조작: a=5, b=5 잠식
    const result = processCentralGap(gap, 5, 5);

    // 결과: 1-2_L(5f), 1-2_R(5f) (1-2_M 소멸)
    console.log("QA-03 Results:", result);

    const pass = result.mid_rem === undefined && result.left_sub?.duration === 5 && result.right_sub?.duration === 5;
    console.log(`QA-03 PASS: ${pass}`);
    return pass;
};

const QA04_Imported_Creation = () => {
    console.log("--- QA-04 ---");
    const A: Fragment = { fragment_id: "A1", source_video: "VA", start_frame: 0, end_frame: 10, duration: 10, selection_state: "S" };
    const B: Fragment = { fragment_id: "B1", source_video: "VB", start_frame: 0, end_frame: 10, duration: 10, selection_state: "N" };

    // B의 일부를 A옆으로 이동 (B 3프레임 잠식)
    const result = applyPairBoundary(A, B, 13);

    // 결과: B_L (Imported sub-fragment) 생성
    console.log("QA-04 Results:", result);

    const pass = result.fB_sel?.fragment_id === "B1_L" && result.fB_sel?.source_video === "VB" && result.fB_sel?.derivedFrom === "B1";
    console.log(`QA-04 PASS: ${pass}`);
    return pass;
};

const QA05_SS_EdgeCase = () => {
    console.log("--- QA-05 ---");
    // (S,S) 진입 시 제약
    const A1: Fragment = { fragment_id: "A1", source_video: "V1", start_frame: 0, end_frame: 10, duration: 10, selection_state: "S" };
    const A2: Fragment = { fragment_id: "A2", source_video: "V1", start_frame: 10, end_frame: 20, duration: 10, selection_state: "S" };

    const pairState = getPairState(A1, A2);
    console.log("QA-05 Pair State:", pairState);

    // UI logic would insert virtual N or use trim handles.
    const pass = pairState === "(S,S)";
    console.log(`QA-05 PASS: ${pass}`);
    return pass;
};

export const runPBETests = () => {
    console.log("RUNNING PBE CORE TESTS...");
    const results = [
        QA01_SN_SameSource(),
        QA02_CrossSource_Remnant(),
        QA03_CrossSource_Disappearance(),
        QA04_Imported_Creation(),
        QA05_SS_EdgeCase()
    ];
    const totalPass = results.every(r => r === true);
    console.log("TOTAL RESULT:", totalPass ? "ALL PASS ✅" : "SOME FAILED ❌");
    return totalPass;
};

if (typeof window !== 'undefined') {
    (window as any).runPBETests = runPBETests;
}
