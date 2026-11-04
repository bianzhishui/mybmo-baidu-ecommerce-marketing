# 百度营销 API 能力索引

> 来源：`baiduads-sdk` 源码反查（129 个 Service / 389 个接口），按能力域归组。
> 用途：透传调用（`bmctl.py call`）时查服务名与方法名；不确定参数结构时先 `--dry-run`。
>
> ⚠️ 当前应用仅有「工具」域权限，下表除「检索与工具」外的绝大多数接口会返回 89406。
>
> 方法名支持小写蛇形（`get_account_info`）或驼峰（`getAccountInfo`），脚本自动归一化；
> `KR` 两个字母必须大写（脚本已处理）。信息流接口需加 `--line feed`。

## 账户与资金（9 个服务 / 13 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `accountService` | 2 | `get_account_info` `update_account_info` | json/sms |
| `accountfeedService` | 2 | `get_account_feed` `update_account_feed` | json/feed |
| `accountshoppingService` | 2 | `get_account_shopping` `update_account_shopping` | json/sms |
| `balanceService` | 1 | `get_balance_info` | json/sms |
| `paymentService` | 1 | `get_payment_record` | json/sms |
| `paymentfeedService` | 1 | `get_payment_history` | json/feed |
| `businesspointService` | 2 | `get_all_business_point` `get_bind_business_point_list` | json/sms |
| `mcchistoryService` | 1 | `get_account_transfer_history` | json/sms |
| `mccfeedService` | 1 | `get_user_list_by_mccid` | json/feed |

## 搜索推广投放（9 个服务 / 32 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `campaignService` | 4 | `add_campaign` `delete_campaign` `get_campaign` `update_campaign` | json/sms |
| `adgroupService` | 4 | `add_adgroup` `delete_adgroup` `get_adgroup` `update_adgroup` | json/sms |
| `keywordService` | 4 | `add_word` `delete_word` `get_word` `update_word` | json/sms |
| `creativeService` | 5 | `add_creative` `delete_creative` `get_creative` `get_creative_template` `update_creative` | json/sms |
| `negativewordService` | 4 | `get_duplicate_negative_words` `update_adgroup_negative_words` `update_adgroup_negative_words_sync` `update_campaign_negative_words_sync` | json/sms |
| `pricestrategyService` | 4 | `add_price_strategy` `delete_price_strategy` `get_price_strategy` `update_price_strategy` | json/sms |
| `adgroupappService` | 3 | `add_adgroup_app_bind` `delete_adgroup_app_bind` `get_adgroup_app_bind` | json/sms |
| `adgroupimagesegmentbindService` | 3 | `add_adgroup_image_segment_bind` `delete_adgroup_image_segment_bind` `get_adgroup_image_segment_bind` | json/sms |
| `autoexpansionService` | 1 | `get_auto_expansion` | json/sms |

## 信息流投放（12 个服务 / 42 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `campaignfeedService` | 4 | `add_campaign_feed` `delete_campaign_feed` `get_campaign_feed` `update_campaign_feed` | json/feed |
| `adgroupfeedService` | 4 | `add_adgroup_feed` `delete_adgroup_feed` `get_adgroup_feed` `update_adgroup_feed` | json/feed |
| `creativefeedService` | 8 | `add_creative_feed` `bind_recommend_reasons` `delete_creative_feed` `get_creative_feed` `get_creative_feed_preview_url_with_preview_source` `get_temp_creative_feed_preview_url` `query_recommend_reasons` `update_creative_feed` | json/feed |
| `searchfeedService` | 7 | `get_app_id_name_feed` `get_auto_bid_cost` `get_biz_area_feed` `get_coordinate_feed` `get_media_packages` `get_medias` `get_ocpc_trans_feed` | json/feed |
| `atpfeedService` | 5 | `add_atp_feed` `bind_atp_feed` `delete_atp_feed` `get_atp_feed` `update_atp_feed` | json/feed |
| `wtpfeedService` | 4 | `add_wtp_feed` `delete_wtp_feed` `get_wtp_feed` `update_wtp_feed` | json/feed |
| `custommpService` | 4 | `add_custom_mp` `delete_custom_mp` `get_custom_mp` `update_custom_mp` | json/feed |
| `assetsharefeedService` | 1 | `add_asset_share_feed` | json/feed |
| `videofeedService` | 1 | `get_video_text_feed` | json/feed |
| `titlerecommendService` | 1 | `get_title` | json/feed |
| `recmwordfeedService` | 1 | `get_recm_word` | json/feed |
| `imageprocessingService` | 2 | `add_crop_image` `get_default_video_cover_feed` | json/feed |

## DPA 动态商品广告（5 个服务 / 32 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `dpaapiproductsetService` | 7 | `add_product_set` `delete_product_set` `get_catalog_fields_info` `get_catalog_material_fields_info` `get_product_set` `get_product_set_by_catalog` `update_product_set` | json/sms |
| `dpaapicreativeService` | 5 | `add_dpa_creative` `delete_dpa_creative` `get_dpa_creative` `get_dpa_material_types` `update_dpa_creative` | json/sms |
| `dpacreativeService` | 10 | `add_creative_group` `add_creatives` `bat_set_range` `delete_creative_group` `delete_creatives` `get_creative_group` `get_creatives` `get_format_templates` `update_creative_group` `update_creatives` | json/sms |
| `dpaadgroupfeedService` | 4 | `add_adgroup_feed` `delete_adgroup_feed` `get_adgroup_feed` `update_adgroup_feed` | json/feed |
| `dpacreativefeedService` | 6 | `add_creative_feed` `delete_creative_feed` `get_creative_feed` `get_creative_preview` `get_symbol_fields` `update_creative_feed` | json/feed |

## 电商与店铺（10 个服务 / 28 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `campaignshoppingService` | 8 | `add_campaign_shopping` `copy_campaign_shopping` `delete_campaign_shopping` `get_anchor` `get_campaign_shopping` `get_interests` `get_product` `update_campaign_shopping` | json/sms |
| `platproductService` | 7 | `delete_product` `get_product_detail` `get_product_list` `get_product_skus` `mod_online_status` `save_or_update_product` `update_stock` | json/sms |
| `platshopService` | 1 | `get_shop_category_list` | json/sms |
| `subshopopenapiService` | 2 | `create_sub_shop` `update_sub_shop` | json/sms |
| `subshopmaterialopenapiService` | 3 | `add_publicity_image` `get_album_types` `remove_publicity_image` | json/sms |
| `fceshopService` | 1 | `get_auto_deeplink` | json/sms |
| `bmcproductService` | 1 | `fast_update_products` | json/sms |
| `bmcdistributionService` | 1 | `get_catalog` | json/sms |
| `wttradeService` | 1 | `get_trade_list` | json/sms |
| `wtmaterialcategoryService` | 3 | `delete_category` `get_category_list` `update_category` | json/sms |

## 订单与交易（5 个服务 / 20 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `orderbusinessService` | 1 | `grant_call_back` | json/sms |
| `platorderbusinessService` | 5 | `confirm_or_cancel_order` `deliver_order` `reject_order` `take_order` `update_remark` | json/sms |
| `platorderbusinessqueryService` | 4 | `get_express_name_list` `get_order_detail` `get_order_express_package` `get_part_consign_order_list` | json/sms |
| `platbusinessorderrefundService` | 5 | `agree_order_refund` `agree_order_return` `query_order_refund_info` `query_order_refund_list` `reject_order_refund` | json/sms |
| `marketapiService` | 5 | `cancel_order` `create_order` `get_order_info` `get_site_info` `preview_site` | json/sms |

## 人群与定向（11 个服务 / 46 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `crowdService` | 4 | `add_crowd` `delete_crowd` `get_crowd` `update_crowd` | json/sms |
| `crowdappinfoService` | 1 | `get_app_info` | json/sms |
| `crowdbindService` | 4 | `add_bind` `delete_bind` `get_bind` `update_bind` | json/sms |
| `crowdfeedService` | 3 | `get_bind_adgroup` `get_eshop_elds_crowds` `get_eshop_trade_crowds` | json/feed |
| `crowdshoppingService` | 1 | `get_eshop_trade_crowds` | json/sms |
| `extaudienceService` | 4 | `create_empty_group` `get_audience_list` `update_audience_dsp` `update_id_upload4_pour` | json/sms |
| `advancedsegmentService` | 4 | `add_segment` `delete_segment` `get_segment` `update_segment` | json/sms |
| `advancedsegmentbindService` | 4 | `add_segment_bind` `delete_segment_bind` `get_segment_bind` `update_segment_bind` | json/sms |
| `segmentshieldService` | 2 | `add_segment_shield` `get_segment_shield_page` | json/sms |
| `shieldService` | 10 | `add_account_exclude_ip` `add_b_shield_policy` `del_account_exclude_ip` `delete_b_shield_black_ip` `delete_b_shield_customer` `delete_b_shield_policy` `update_b_shield_black_ip` `update_b_shield_customer` `update_policy_ipto_black_ip` `update_shield_policy` | json/sms |
| `rtafeedService` | 9 | `add_rta_setting` `del_rta_setting` `del_strategy` `get_configurable_users` `get_rta_setting` `get_rta_token` `get_strategy` `update_rta_setting` `update_strategy` | json/sms |

## 转化追踪与线索（11 个服务 / 24 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `traceapiService` | 1 | `update_trans_trace` | json/feed |
| `traceurlService` | 1 | `get_promotion_urls` | json/sms |
| `ocpcService` | 5 | `add_target_package` `delete_target_package` `get_hint_audit_time` `get_target_package_list` `update_target_package` | json/sms |
| `ocpctransfeedService` | 1 | `add_ocpc_trans_feed` | json/feed |
| `fctranstraceapiService` | 4 | `add_fc_trans_trace` `delete_fc_trans_trace` `get_fc_trans_trace_list` `update_fc_trans_trace` | json/sms |
| `fcocpcService` | 1 | `get_suggest_cpas` | json/sms |
| `leadadsService` | 5 | `add_strategies` `delete_strategies` `get_materials` `get_strategies` `update_strategies` | json/sms |
| `cluescoreService` | 3 | `get_clue_result_file_url` `query_clue_task_status` `submit_clue_task` | json/sms |
| `fmleadsupdateService` | 1 | `add_mark` | json/sms |
| `fmphoneoutsideapiService` | 1 | `get_virtual_phone` | json/sms |
| `leadsnoticeService` | 1 | `get_notice_list` | json/sms |

## 素材与创意生产（25 个服务 / 77 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `imagemanageService` | 4 | `del_image` `get_image_list` `mod_image` `upload_image` | json/sms |
| `imagemanagementService` | 2 | `get_video_extract_image` `upload_image` | json/sms |
| `imageintelligentService` | 1 | `get_smart_template_image` | json/sms |
| `imagesegmentService` | 4 | `add_image_segment` `delete_image_segment` `get_image_segment` `update_image_segment` | json/sms |
| `videouploadService` | 1 | `add_video` | json/sms |
| `videoService` | 2 | `delete_videos` `get_video_infos` | json/sms |
| `videocontentService` | 1 | `query_content` | json/sms |
| `videoediterService` | 2 | `smart_audio` `smart_music` | json/sms |
| `videosynthetiseService` | 8 | `clip_video` `get_smart_audio_status` `get_task_videos` `push_smart_video` `push_video` `query_video_clip_status` `smart_synthetise` `synthetise_status` | json/sms |
| `materialarticleService` | 7 | `add_article` `delete_article` `get_article_list` `update_article` `update_category` `update_putaway` `update_rank` | json/sms |
| `materialbrandmodService` | 4 | `add_brand` `delete_brand` `update_brand` `update_putaway` | json/sms |
| `materialbrandqueryService` | 1 | `get_brand_list` | json/sms |
| `materialbindmodService` | 3 | `add_material_bind` `delete_material_bind` `update_material_bind` | json/sms |
| `materialcenterbindqueryService` | 1 | `get_material_bind` | json/sms |
| `materialpersonmodService` | 6 | `add_person` `delete_person` `update_category` `update_person` `update_putaway` `update_rank` | json/sms |
| `materialpersonqueryService` | 1 | `get_person_list` | json/sms |
| `materialproductService` | 7 | `add_product` `delete_product` `get_product_list` `update_category` `update_product` `update_putaway` `update_rank` | json/sms |
| `materialquestionmodService` | 6 | `add_question` `delete_question` `update_category` `update_putaway` `update_question` `update_rank` | json/sms |
| `materialquestionqueryService` | 1 | `get_question_list` | json/sms |
| `materialtradequeryService` | 1 | `get_user_trade` | json/sms |
| `wordmaterialService` | 1 | `search` | json/sms |
| `huituapiv2Service` | 1 | `get_user_template` | json/sms |
| `creativesuggestService` | 1 | `get_creative_segment_recommend` | json/sms |
| `danubecreativegroupService` | 6 | `add_danube_creative_group` `copy_danube_creative_group` `delete_danube_creative_group` `get_danube_constants` `get_danube_creative_group` `update_danube_creative_group` | json/sms |
| `cyctemplateService` | 5 | `add_template` `delete_template` `get_bind_cyc_template` `get_template` `update_template` | json/sms |

## 报告与诊断优化（11 个服务 / 23 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `openapireportService` | 3 | `create_report_task` `get_report_data` `get_task_status` | json/sms |
| `fluctuationanalysisService` | 1 | `query_fluctuation_reasons` | json/sms |
| `feeddiagnosisService` | 1 | `query_feed_unit_diagnosis_detail` | json/sms |
| `growthpowerService` | 2 | `get_growth_power_detail` `get_growth_power_overview` | json/sms |
| `styleanalyseService` | 1 | `decode` | json/sms |
| `videodataService` | 2 | `get_label_data` `get_second_level_data` | json/sms |
| `optimizationcenterService` | 1 | `get_adgroup_recommend_hot_query_word` | json/sms |
| `adviceService` | 6 | `accept_advice` `accept_feed_advice` `download_advice` `query_detail` `query_feed_detail` `query_feed_outline` | json/sms |
| `advicesettingService` | 1 | `mod_setting` | json/sms |
| `advicelandingpageapiService` | 2 | `query_landing_page_correlation` `query_landing_page_quality` | json/sms |
| `industrytrafficService` | 3 | `get_search_trend_by_dev2` `get_search_word_list` `get_trade_node_list_v2` | json/sms |

## 检索与工具（17 个服务 / 40 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `searchService` | 5 | `get_count_by_id` `get_creative_id_by_search` `get_ids_by_tabs` `get_keyword_id_by_search` `get_material_info_by_search` | json/sms |
| `feedmaterialsearchService` | 1 | `get_material_info_by_search` | json/sms |
| `appfeedService` | 1 | `get_js_kp_app_list` | json/feed |
| `krService` | 5 | `get_file_path` `get_file_status` `get_kr_custom` `get_kr_file_id_by_words` `get_krby_query` | json/sms |
| `indexapiService` | 4 | `check_keywords` `create_task` `get_result` `refresh_access_token` | json/sms |
| `bulkjobService` | 7 | `cancel_download` `get_all_changed_objects` `get_all_objects` `get_changed_item_id` `get_changed_scale` `get_file_path` `get_file_status` | json/sms |
| `bulkjobfeedService` | 4 | `cancel_download` `get_all_feed_objects` `get_file_path` `get_file_status` | json/sms |
| `preauditService` | 1 | `material_pre_audit` | json/sms |
| `toolkitService` | 1 | `get_operation_record` | json/sms |
| `streamapiuploadService` | 1 | `upload_id_stream` | json/sms |
| `apidataassetService` | 2 | `create_data_asset` `submit_data_asset_task` | json/sms |
| `appcenterjobService` | 3 | `add_batch_packages` `get_batch_job_details` `get_batch_job_list_results` | json/sms |
| `appcenterpackageService` | 1 | `get_app_packagelist` | json/sms |
| `appprocessService` | 1 | `get_app_list` | json/sms |
| `tabService` | 1 | `get_tabs` | json/sms |
| `pageService` | 1 | `get_broad_cast_pages` | json/sms |
| `teslacommonrecordService` | 1 | `get_dict_info` | json/sms |

## 建站落地页与小程序（4 个服务 / 12 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `jmysiteService` | 6 | `create_page` `delete_page` `edit_page` `get_page_detail` `get_page_list` `preview_page` | json/sms |
| `miniprogramService` | 1 | `get_mini_programs` | json/sms |
| `shareService` | 1 | `save_sharing_batch_dr` | json/sms |
| `sharerepertoryService` | 4 | `add_share_repertory` `delete_share_repertory` `get_share_repertory` `update_share_repertory` | json/sms |

## 手写部分（4 个服务 / 10 个接口）

| 服务类 | 接口数 | 方法 | 产品线 |
|---|---:|---|---|
| `OAuthService` | 4 | `getAccessToken` `refreshToken` `getUserInfo` `getOpenId` | - |
| `MarketingFileService` | 1 | `uploadFile` | sms |
| `UploadClient(分片上传)` | 4 | `initMultipartUpload` `uploadPart` `completeMultipartUpload` `abortMultipartUpload` | - |
| `VideoUploadService` | 1 | `addVideo` | sms |
