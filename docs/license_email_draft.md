# License Inquiry Email Draft

> 발송 대상: Julian McAuley, UC San Diego (`jmcauley@ucsd.edu`)
> 목적: Amazon-Reviews-2023 dataset의 상업적 사용 라이선스 확인
> 발송자: 직접 보내야 함 (이메일 클라이언트에서)

---

## Recommended (영문 — 학술 메일 톤)

**Subject**: Commercial use of Amazon-Reviews-2023 dataset for product research tooling

Dear Prof. McAuley,

I am building a small internal tool that uses publicly-available Amazon
product metadata to score category demand for dropshipping decisions.
The tool relies on item-level fields (parent_asin, title, brand,
rating_number, average_rating, main_category) from the
`McAuley-Lab/Amazon-Reviews-2023` dataset on Hugging Face.

I noticed the dataset's Hugging Face page does not list an explicit
license, and the README points only to the NAACL 2024 paper. Before
deploying the tool in a commercial context, I would like to confirm:

1. Is the dataset released under a permissive license that allows
   commercial use, with appropriate attribution to your lab and the
   NAACL 2024 paper?
2. If yes, what citation/attribution form do you prefer?
3. If commercial use requires a separate agreement, what would be the
   appropriate next step?

I am happy to share more details about the tool and the specific fields
I rely on if it would help your decision.

Thank you for releasing such a valuable dataset, and for your time.

Best regards,
[Your Name]
[Your Title / Company, if any]
[Your Email]

---

## Optional citation block to include

```
@inproceedings{hou2024bridging,
  title     = {Bridging Language and Items for Retrieval and Recommendation},
  author    = {Hou, Yupeng and Li, Jiacheng and He, Zhankui and Yan, An 
               and Chen, Xiusi and McAuley, Julian},
  booktitle = {arXiv preprint arXiv:2403.03952},
  year      = {2024}
}
```

---

## 발송 후 처리

회신 받으면:
1. 허가 명확: 그대로 사용 + README/UI에 라이선스 출처 표기
2. 조건부 허가: 조건 충족 후 사용
3. 거절: HF dataset 사용 중단 → Common Crawl 또는 자체 스크래핑으로 전환
4. 무회신 (2주 후): 학술 공개 관행 기준으로 사용 + 적극 attribution
