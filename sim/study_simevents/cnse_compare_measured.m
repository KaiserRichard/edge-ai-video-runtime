function comparison = cnse_compare_measured(root, simulated)
% Combine the measured CSV and additional endpoints from the hardware tables.
csv = "data/cn_targets.csv";
snapshot = "data/source/cn_hw_tables.md";
comparison = readtable(fullfile(root,csv),'TextType','string');
metrics = ["sequence_loss","frame_loss","on_time","late","latency_p50_ms", ...
    "latency_p95_ms","jitter_ms","aoi_ms"];
comparison = comparison(ismember(comparison.metric,metrics),:);
comparison.source = repmat(csv,height(comparison),1);

section = "";
for line = strip(readlines(fullfile(root,snapshot)))'
    if startsWith(line,"### CN-T") || startsWith(line,"## CN-T")
        section = string(regexp(line,'CN-T\d+','match','once'));
    end
    if ~startsWith(line,"|")
        continue
    end
    cellText = strip(split(line,'|'));
    config = cellText(2);
    if section == "CN-T7"
        config = "T7_" + config;
    end
    if ~ismember(config,simulated.config)
        continue
    end
    switch section
        case {"CN-T2","CN-T3","CN-T4"}
            add(config,"sequence_loss",str2double(cellText(6)),"fraction");
            add(config,"frame_loss",str2double(cellText(8)),"fraction");
            add(config,"on_time",str2double(cellText(10)),"fraction");
            add(config,"late",str2double(cellText(11)),"fraction");
            add(config,"latency_p95_ms",str2double(cellText(14)),"ms");
        case "CN-T5"
            add(config,"sequence_loss",str2double(cellText(10)),"fraction");
        case "CN-T6"
            add(config,"sequence_loss",str2double(cellText(5)),"fraction");
        case "CN-T7"
            endpoint = str2double(strip(split(cellText(9),'/')));
            add(config,"latency_p50_ms",endpoint(1),"ms");
            add(config,"latency_p95_ms",endpoint(2),"ms");
    end
end

[found, location] = ismember(comparison.config,simulated.config);
assert(all(found),'CNSE:MeasuredConfig','A measured condition has no simulation.');
comparison.simulated = NaN(height(comparison),1);
for k = 1:height(comparison)
    values = simulated.(comparison.metric(k));
    comparison.simulated(k) = values(location(k));
end
comparison.signed_error = comparison.simulated - comparison.value;
comparison.relative_error = NaN(height(comparison),1);
nonzero = comparison.value ~= 0;
comparison.relative_error(nonzero) = comparison.signed_error(nonzero)./comparison.value(nonzero);
comparison = sortrows(comparison,{'config','metric'});

    function add(config,metric,value,unit)
        if ~isfinite(value) || any(comparison.config==config & comparison.metric==metric)
            return
        end
        evidence = "MEASURED_5_runs";
        if section == "CN-T6"
            evidence = "MEASURED_descriptive";
        end
        comparison(end+1,:) = {config,metric,value,unit,evidence,snapshot};
    end
end
