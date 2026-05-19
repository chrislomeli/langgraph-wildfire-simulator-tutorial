create table resources
(
    resource_id            integer not null
        constraint resources_pk
            primary key,
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
    location               geography(Point, 4326)
);

alter table resources
    owner to chrislomeli;

create table spatial_ref_sys
(
    srid      integer not null
        primary key
        constraint spatial_ref_sys_srid_check
            check ((srid > 0) AND (srid <= 998999)),
    auth_name varchar(256),
    auth_srid integer,
    srtext    varchar(2048),
    proj4text varchar(2048)
);

alter table spatial_ref_sys
    owner to chrislomeli;

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
    constraint terrain_pk
        unique (grid_column, grid_row)
);

alter table terrain
    owner to chrislomeli;

create table sensors
(
    grid_row    integer,
    grid_column integer,
    elevation   integer,
    sensor_id   varchar(60) not null
        constraint sensors_pk
            primary key,
    sensor_type varchar(30),
    cluster_id  varchar(60),
    noise_std   double precision,
    lat         double precision,
    long        double precision,
    location    geography(Point, 4326),
    region      varchar(60)
);

alter table sensors
    owner to chrislomeli;

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

alter table wildfire_activity
    owner to chrislomeli;

create table resource_assignments
(
    resource_id            integer,
    fire_id                integer,
    commitment_level       integer,
    commitment_start_days  integer,
    commitment_length_days integer
);

comment on column resource_assignments.commitment_start_days is 'days since committment started - for simulation backdate this many days to get s start date';

alter table resource_assignments
    owner to chrislomeli;

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

alter table current_fires
    owner to chrislomeli;

create table resource_advisories
(
    id                   uuid                                      not null
        primary key,
    created_at           timestamp with time zone                  not null,
    status               varchar default 'SENT'::character varying not null
        constraint resource_advisories_status_check
            check ((status)::text = ANY
                   ((ARRAY ['SENT'::character varying, 'SUPPRESSED'::character varying, 'ACKNOWLEDGED'::character varying])::text[])),
    epicenter_row        integer                                   not null,
    epicenter_column     integer                                   not null,
    location_description varchar                                   not null,
    situation            text                                      not null,
    urgency_level        integer                                   not null
        constraint valid_urgency
            check ((urgency_level >= 1) AND (urgency_level <= 4)),
    notes                text                                      not null,
    recommendation       text                                      not null
);

alter table resource_advisories
    owner to chrislomeli;

create index idx_resource_advisories_guardrail
    on resource_advisories (epicenter_row, epicenter_column, status, created_at);

create table cell_state
(
    state_group        varchar(40)                not null,
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
    risk_score         integer          default 0 not null,
    confidence         integer          default 0 not null,
    region             varchar(60),
    constraint cell_state_pk
        unique (state_group, grid_row, grid_column, layer, region)
);

alter table cell_state
    owner to chrislomeli;


create table scenario_cell_plan
(
    region         varchar(60)                  not null,
    grid_row       integer                      not null,
    grid_column    integer                      not null,
    layer          integer     default 0        not null,
    metric         varchar(20)                  not null,
    start_tick     integer     default 0        not null,
    duration_ticks integer                      not null,
    start_value    real,
    target_value   real                         not null,
    curve          varchar(12) default 'linear' not null,
    hold_after     boolean     default true     not null,
    constraint scenario_cell_plan_pk
        unique (region, grid_row, grid_column, layer, metric, start_tick),
    constraint scp_metric_ck
        check (metric in ('temperature_c', 'humidity_pct', 'wind_speed_mps',
                          'wind_direction_deg', 'pressure_hpa', 'fuel_moisture')),
    constraint scp_curve_ck
        check (curve in ('linear', 'ease_in', 'ease_out', 'step')),
    constraint scp_dur_ck
        check (duration_ticks >= 1)
);

alter table scenario_cell_plan
    owner to chrislomeli;


create view v_cell_plan as
select cs.region,
       cs.grid_row,
       cs.grid_column,
       cs.layer,
       cs.temperature_c,
       cs.humidity_pct,
       cs.wind_speed_mps,
       cs.fuel_moisture,
       coalesce(
               json_agg(
               json_build_object(
                       'metric', p.metric,
                       'start_tick', p.start_tick,
                       'duration_ticks', p.duration_ticks,
                       'start_value', p.start_value,
                       'target_value', p.target_value,
                       'curve', p.curve,
                       'hold_after', p.hold_after
                   ) order by p.metric, p.start_tick
                       ) filter (where p.metric is not null),
               '[]'
       ) as plan
from cell_state cs
         left join scenario_cell_plan p
                   on p.region = cs.region
                       and p.grid_row = cs.grid_row
                       and p.grid_column = cs.grid_column
                       and p.layer = cs.layer
where cs.state_group = 'seed'
group by cs.region, cs.grid_row, cs.grid_column, cs.layer,
         cs.temperature_c, cs.humidity_pct, cs.wind_speed_mps, cs.fuel_moisture;

