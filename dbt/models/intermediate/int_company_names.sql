-- One row per company (ISIN) and financial year: cleaned company name, CIN and symbol(s).
-- Name source: the XBRL fact NameOfTheCompany, falling back to the NSE listing name when the XBRL
-- text is broken (U+FFFD). Cleaning: broken characters and bracketed abbreviations removed,
-- "Ltd" written as "Limited", and ALL-CAPS variants replaced by the mixed-case spelling the same
-- company used in another year (title case if it never used one).
-- Several filings for the same ISIN and year (revisions): the latest period end / filing wins.

with filings as (
    select
        filing_id,
        isin,
        symbol,
        fiscal_year_label,
        period_end,
        taxonomy_version
    from {{ ref('stg_filings') }}
),

listing as (
    select
        filing_id,
        symbol as listing_symbol,
        company_name as listing_name
    from {{ ref('stg_listing') }}
),

identity_facts as (
    select
        filing_id,
        max(case when concept = 'NameOfTheCompany' then raw_value end) as xbrl_name,
        max(case when concept = 'CorporateIdentityNumber' then raw_value end) as cin_filed
    from {{ ref('stg_facts') }}
    where concept in ('NameOfTheCompany', 'CorporateIdentityNumber') and not is_nil
    group by filing_id
),

ranked as (
    select
        filings.*,
        listing.listing_symbol,
        listing.listing_name,
        identity_facts.xbrl_name,
        identity_facts.cin_filed,
        row_number() over (
            partition by filings.isin, filings.fiscal_year_label
            order by filings.period_end desc, filings.filing_id desc
        ) as rn
    from filings
    left join listing on filings.filing_id = listing.filing_id
    left join identity_facts on filings.filing_id = identity_facts.filing_id
),

picked as (
    select
        *,
        case
            when coalesce(trim(xbrl_name), '') != '' and not contains(xbrl_name, chr(65533))
                then xbrl_name
            else coalesce(nullif(trim(listing_name), ''), xbrl_name)
        end as name_filed
    from ranked
    where rn = 1
),

cleaned as (
    select
        *,
        trim(
            regexp_replace(
                regexp_replace(
                    regexp_replace(
                        replace(
                            replace(replace(name_filed, chr(65533), ''), chr(8217), chr(39)),
                            chr(8220), ''
                        ),
                        '\s*\([^)]*\)', '', 'g'
                    ),
                    '\s+', ' ', 'g'
                ),
                '(?i)\s+ltd\.?$', ' Limited'
            )
        ) as name_cleaned
    from picked
),

mixed_case_variant as (
    -- the latest mixed-case spelling of each name, per company
    select
        isin,
        lower(name_cleaned) as name_key,
        arg_max(name_cleaned, fiscal_year_label) as mixed_case_name
    from cleaned
    where name_cleaned != upper(name_cleaned)
    group by isin, lower(name_cleaned)
)

select
    cleaned.isin,
    cleaned.fiscal_year_label,
    cleaned.filing_id,
    cleaned.symbol,
    list_aggr(
        list_sort(
            list_distinct(list_filter([cleaned.symbol, cleaned.listing_symbol], x -> x is not null))
        ),
        'string_agg', ', '
    ) as symbols,
    cleaned.xbrl_name as company_name_filed,
    cleaned.listing_name,
    coalesce(
        case
            when cleaned.name_cleaned = upper(cleaned.name_cleaned)
                then mixed_case_variant.mixed_case_name
        end,
        -- no mixed-case spelling in any year: title-case the ALL-CAPS name
        case
            when cleaned.name_cleaned = upper(cleaned.name_cleaned)
                then array_to_string(
                    list_transform(
                        string_split(lower(cleaned.name_cleaned), ' '),
                        w -> upper(left(w, 1)) || substr(w, 2)
                    ),
                    ' '
                )
            else cleaned.name_cleaned
        end
    ) as company_name_clean,
    case
        -- 99999 is a real industry code in a CIN ("unclassified", e.g. L&T); a placeholder is
        -- recognised by its shape (SBIN files Z99999ZZ9999ZZZ999999 and A00000AA0000AAA000000)
        when regexp_matches(cleaned.cin_filed, '^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$')
            then cleaned.cin_filed
    end as cin,
    cleaned.cin_filed,
    cleaned.taxonomy_version
from cleaned
left join mixed_case_variant
    on
        cleaned.isin = mixed_case_variant.isin
        and lower(cleaned.name_cleaned) = mixed_case_variant.name_key
