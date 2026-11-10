# Integration plan

1. Stash P4's untracked artifacts; create integration/p1-p5 from the P5 checkout.
2. Merge origin/main (P1), origin/p2/platform and origin/p3. Preserve all dependencies,
   regenerate uv.lock from the baseline and restore P4 without dropping the safety stash.
3. Adapt P4 task names, Completion.route identity and verification_scope to actual P3.
4. Validate P4 graph/item exports with P1 models; mount P3's router factories in P2.
5. Align public input conventions and normalize DB percent progress to P1's 0..1.
6. Test P5 against P1 fixture files; handle nullable traces and confirm API config defaults.
7. Export the integrated OpenAPI, run offline suites plus lint/types/build, document
   DB/model/worker gaps and leave the local frontend running for user inspection.
