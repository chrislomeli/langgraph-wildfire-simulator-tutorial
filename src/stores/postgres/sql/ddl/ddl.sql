create table resources
(
    resource_id            integer not null,
    source_file            varchar(30),
    agency                 varchar(60),
    cal_file_unit          varchar(30),
    unit_id                varchar(30),
    resource_category      varchar(30),
    resource_type          varchar(60),
    nwcg_type              varchar(30),
    year                   varchar(10),
    make                   varchar(30),
    model                  varchar(10),
    capacity_water_gal     integer,
    pump_gpm               integer,
    personnel              integer,
    battalion              varchar(30),
    station_number         varchar(10),
    station_name           varchar(60),
    station_address        varchar(60),
    mutual_aid_agreement   varchar(30),
    lpf_interface_priority varchar(30),
    seasonal               varchar(10),
    lat                    double precision,
    long                   double precision,
    notes                  text,
    location               geography(Point, 4326),
    constraint resources_pk
        primary key (resource_id)
);

create table spatial_ref_sys
(
    srid      integer not null,
    auth_name varchar(256),
    auth_srid integer,
    srtext    varchar(2048),
    proj4text varchar(2048),
    primary key (srid),
    constraint spatial_ref_sys_srid_check
        check ((srid > 0) AND (srid <= 998999))
);

grant select on spatial_ref_sys to public;

create table terrain
(
    grid_column         integer,
    grid_row            integer,
    layer               integer,
    cell_key            varchar(30),
    terrain             varchar(30),
    vegetation          double precision,
    slope               real,
    cell_size_ft        integer,
    time_step_min       real,
    burn_duration_ticks integer,
    lat                 double precision,
    long                double precision,
    location            geography(Point, 4326),
    region              varchar(60),
    terrain_type        varchar(20),
    property_stake      varchar(10) default 'none'::character varying not null,
    life_stake          varchar(10) default 'none'::character varying not null,
    stake_notes         text,
    constraint terrain_pk
        unique (grid_column, grid_row),
    constraint terrain_property_stake_ck
        check ((property_stake)::text = ANY
               ((ARRAY ['none'::character varying, 'low'::character varying, 'moderate'::character varying, 'high'::character varying])::text[])),
    constraint terrain_life_stake_ck
        check ((life_stake)::text = ANY
               ((ARRAY ['none'::character varying, 'low'::character varying, 'moderate'::character varying, 'high'::character varying])::text[]))
);

create table sensors
(
    grid_row    integer,
    grid_column integer,
    elevation   integer,
    sensor_id   varchar(60) not null,
    sensor_type varchar(30),
    cluster_id  varchar(60),
    noise_std   double precision,
    lat         double precision,
    long        double precision,
    location    geography(Point, 4326),
    region      varchar(60),
    constraint sensors_pk
        primary key (sensor_id)
);

create table wildfire_activity
(
    imsr_date            date,
    gacc                 varchar(30),
    gacc_priority        integer,
    fire_priority        integer,
    new_large_fire_mark  varchar(10) not null,
    fire_name            varchar(120),
    unit                 varchar(30),
    fire_size_acres      integer,
    fire_size_change     varchar(20),
    percent_containment  integer,
    contained_completed  varchar(30),
    est_containment_date varchar(30),
    personnel            integer,
    personnel_change     varchar(30),
    crews                integer,
    engines              integer,
    helicopters          integer,
    structures_lost      integer,
    cost_to_date         varchar(20),
    origin_ownership     varchar(60)
);

create table resource_assignments
(
    resource_id            integer,
    fire_id                integer,
    commitment_level       integer,
    commitment_start_days  integer,
    commitment_length_days integer
);

comment on column resource_assignments.commitment_start_days is 'days since committment started - for simulation backdate this many days to get s start date';

create table current_fires
(
    imsr_date           date,
    gacc                varchar(30),
    gacc_priority       integer,
    fire_priority       integer,
    new_large_fire_mark varchar(10),
    fire_name           varchar(120),
    unit                varchar(30),
    fire_size_acres     integer,
    fire_size_change    varchar(20),
    percent_containment integer,
    contained_completed varchar(30),
    personnel           integer,
    personnel_change    varchar(30),
    crews               integer,
    engines             integer,
    helicopters         integer,
    structures_lost     integer,
    cost_to_date        varchar(20),
    origin_ownership    varchar(60),
    lat                 double precision,
    long                double precision,
    location            geography(Point, 4326),
    fire_id             integer
);

create table resource_advisories
(
    id                   uuid                                      not null,
    created_at           timestamp with time zone                  not null,
    status               varchar default 'SENT'::character varying not null,
    epicenter_row        integer                                   not null,
    epicenter_column     integer                                   not null,
    location_description varchar                                   not null,
    situation            text                                      not null,
    urgency_level        integer                                   not null,
    notes                text                                      not null,
    recommendation       text                                      not null,
    primary key (id),
    constraint resource_advisories_status_check
        check ((status)::text = ANY
               ((ARRAY ['SENT'::character varying, 'SUPPRESSED'::character varying, 'ACKNOWLEDGED'::character varying])::text[])),
    constraint valid_urgency
        check ((urgency_level >= 1) AND (urgency_level <= 4))
);

create index idx_resource_advisories_guardrail
    on resource_advisories (epicenter_row, epicenter_column, status, created_at);

create table cell_state
(
    version            varchar(40)                not null,
    grid_row           integer                    not null,
    grid_column        integer                    not null,
    layer              integer          default 0 not null,
    temperature_c      real,
    humidity_pct       real,
    wind_speed_mps     real,
    wind_direction_deg real,
    pressure_hpa       real,
    fuel_moisture      double precision,
    fire_intensity     double precision default 0 not null,
    region             varchar(60),
    vegetation         double precision,
    constraint cell_state_pk
        unique (version, grid_row, grid_column, layer, region)
);

comment on column cell_state.vegetation is ' < 0     | water/cloud/snow/invalid  :: 0.0–0.1 | bare ground / rock  :: 0.1–0.3 | sparse vegetation :: 0.3–0.5 | moderate vegetation   :: 0.5–0.8 | dense healthy vegetation  ::| > 0.8   | extremely lush vegetation | ';

create table cell_escalation
(
    version          varchar(40)                            not null,
    grid_row         integer                                not null,
    grid_column      integer                                not null,
    layer            integer                  default 0     not null,
    region           varchar(60)                            not null,
    tick             integer                                not null,
    escalate         boolean                                not null,
    confidence       integer                                not null,
    property_at_risk varchar(10)                            not null,
    life_at_risk     varchar(10)                            not null,
    rationale        text                                   not null,
    created_at       timestamp with time zone default now() not null,
    constraint cell_escalation_pk
        unique (version, region, grid_row, grid_column, layer, tick),
    constraint cell_escalation_confidence_ck
        check ((confidence >= 1) AND (confidence <= 10)),
    constraint cell_escalation_property_ck
        check ((property_at_risk)::text = ANY
               ((ARRAY ['none'::character varying, 'low'::character varying, 'moderate'::character varying, 'high'::character varying])::text[])),
    constraint cell_escalation_life_ck
        check ((life_at_risk)::text = ANY
               ((ARRAY ['none'::character varying, 'low'::character varying, 'moderate'::character varying, 'high'::character varying])::text[]))
);

create index idx_cell_escalation_lookup
    on cell_escalation (region, tick, escalate);

create table scenarios
(
    scenario_id   serial,
    name          varchar(120)                           not null,
    description   text,
    version       integer                  default 1     not null,
    region        varchar(60)                            not null,
    horizon_ticks integer                                not null,
    created_at    timestamp with time zone default now() not null,
    primary key (scenario_id),
    constraint scenarios_name_version_uk
        unique (name, version)
);

create table scenario_cell_plan
(
    region         varchar(60)       not null,
    grid_row       integer           not null,
    grid_column    integer           not null,
    layer          integer default 0 not null,
    metric         varchar(20)       not null,
    start_tick     integer default 0 not null,
    duration_ticks integer           not null,
    start_value    real,
    target_value   real              not null,
    scenario_id    integer,
    constraint scenario_cell_plan_pk
        unique (scenario_id, grid_row, grid_column, layer, metric, start_tick),
    foreign key (scenario_id) references scenarios,
    constraint scp_dur_ck
        check (duration_ticks >= 1),
    constraint scp_metric_ck
        check ((metric)::text = ANY
               ((ARRAY ['temperature_c'::character varying, 'humidity_pct'::character varying, 'wind_speed_mps'::character varying, 'wind_direction_deg'::character varying, 'pressure_hpa'::character varying, 'fuel_moisture'::character varying, 'vegetation'::character varying])::text[]))
);

create table expected_escalation
(
    scenario_id               integer                      not null,
    grid_row                  integer                      not null,
    grid_column               integer                      not null,
    layer                     integer default 0            not null,
    expected_escalate         boolean                      not null,
    expected_property_at_risk varchar(10)                  not null,
    expected_life_at_risk     varchar(10)                  not null,
    rationale_keywords        text[]  default '{}'::text[] not null,
    notes                     text,
    constraint expected_escalation_pk
        unique (scenario_id, grid_row, grid_column, layer),
    foreign key (scenario_id) references scenarios,
    constraint expected_escalation_property_ck
        check ((expected_property_at_risk)::text = ANY
               ((ARRAY ['none'::character varying, 'low'::character varying, 'moderate'::character varying, 'high'::character varying])::text[])),
    constraint expected_escalation_life_ck
        check ((expected_life_at_risk)::text = ANY
               ((ARRAY ['none'::character varying, 'low'::character varying, 'moderate'::character varying, 'high'::character varying])::text[]))
);

create table eval_runs
(
    eval_run_id    serial,
    scenario_id    integer                  not null,
    model_label    varchar(60)              not null,
    prompt_version varchar(30)              not null,
    started_at     timestamp with time zone not null,
    finished_at    timestamp with time zone,
    pass_count     integer,
    fail_count     integer,
    notes          text,
    primary key (eval_run_id),
    foreign key (scenario_id) references scenarios
);

create table eval_results
(
    eval_run_id             integer           not null,
    grid_row                integer           not null,
    grid_column             integer           not null,
    layer                   integer default 0 not null,
    actual_escalate         boolean           not null,
    actual_confidence       integer           not null,
    actual_property_at_risk varchar(10)       not null,
    actual_life_at_risk     varchar(10)       not null,
    actual_rationale        text              not null,
    passed                  boolean           not null,
    escalate_match          boolean           not null,
    property_distance       integer           not null,
    life_distance           integer           not null,
    constraint eval_results_pk
        unique (eval_run_id, grid_row, grid_column, layer),
    foreign key (eval_run_id) references eval_runs
);

create table terrain_backup
(
    grid_column         integer,
    grid_row            integer,
    layer               integer,
    cell_key            varchar(30),
    terrain             varchar(30),
    vegetation          double precision,
    slope               real,
    cell_size_ft        integer,
    time_step_min       real,
    burn_duration_ticks integer,
    lat                 double precision,
    long                double precision,
    location            geography(Point, 4326),
    region              varchar(60),
    terrain_type        varchar(20),
    property_stake      varchar(10),
    life_stake          varchar(10),
    stake_notes         text
);

