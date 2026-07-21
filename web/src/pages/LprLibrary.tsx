import { useApiHost } from "@/api";
import { CameraNameLabel } from "@/components/camera/FriendlyNameLabel";
import ActivityIndicator from "@/components/indicators/activity-indicator";
import TextEntryDialog from "@/components/overlay/dialog/TextEntryDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Toaster } from "@/components/ui/sonner";
import { use24HourTime, useFormattedTimestamp } from "@/hooks/use-date-utils";
import { FrigateConfig } from "@/types/frigateConfig";
import { PlateSortType, PlateSummary } from "@/types/lpr";
import axios, { AxiosError } from "axios";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { LuCar, LuSearch } from "react-icons/lu";
import { HiOutlineDotsVertical } from "react-icons/hi";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import useSWR from "swr";

export default function LprLibrary() {
  const { t } = useTranslation(["views/lprLibrary"]);
  const { data: config, mutate: updateConfig } = useSWR<FrigateConfig>(
    "config",
    {
      revalidateOnFocus: false,
    },
  );

  useEffect(() => {
    document.title = t("documentTitle");
  }, [t]);

  const { data: plates, mutate: refreshPlates } = useSWR<PlateSummary[]>(
    config?.lpr?.enabled ? "lpr/plates" : null,
  );

  // filtering and sorting

  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<PlateSortType>("last_seen");

  const visiblePlates = useMemo(() => {
    if (!plates) {
      return [];
    }

    const query = filter.trim().toLowerCase();
    const filtered = query
      ? plates.filter(
          (summary) =>
            summary.plate.toLowerCase().includes(query) ||
            summary.known_name?.toLowerCase().includes(query),
        )
      : [...plates];

    switch (sort) {
      case "count":
        return filtered.sort((a, b) => b.count - a.count);
      case "plate":
        return filtered.sort((a, b) => a.plate.localeCompare(b.plate));
      default:
        return filtered.sort((a, b) => b.latest_time - a.latest_time);
    }
  }, [plates, filter, sort]);

  // known plates management

  const [assignPlate, setAssignPlate] = useState<PlateSummary | null>(null);

  const saveKnownPlates = useCallback(
    async (newKnownPlates: { [name: string]: string[] | null }) => {
      try {
        await axios.put("config/set", {
          requires_restart: 0,
          config_data: { lpr: { known_plates: newKnownPlates } },
        });
        updateConfig();
        refreshPlates();
        toast.success(t("toast.success.updatedKnownPlates"), {
          position: "top-center",
        });
      } catch (error) {
        const axiosError = error as AxiosError<{ message?: string }>;
        toast.error(
          t("toast.error.updateKnownPlatesFailed", {
            errorMessage:
              axiosError.response?.data?.message ?? axiosError.message,
          }),
          { position: "top-center" },
        );
      }
    },
    [refreshPlates, t, updateConfig],
  );

  const buildKnownPlatesWithoutPlate = useCallback(
    (plate: string) => {
      const current = config?.lpr?.known_plates ?? {};
      const updated: { [name: string]: string[] | null } = {};

      Object.entries(current).forEach(([name, namePlates]) => {
        const remaining = (namePlates ?? []).filter((item) => item !== plate);
        // a null value deletes the name from the configuration
        updated[name] = remaining.length > 0 ? remaining : null;
      });

      return updated;
    },
    [config],
  );

  const handleAssignName = useCallback(
    (name: string) => {
      if (!assignPlate) {
        return;
      }

      const trimmed = name.trim();

      if (!trimmed) {
        return;
      }

      const updated = buildKnownPlatesWithoutPlate(assignPlate.plate);
      updated[trimmed] = [...(updated[trimmed] ?? []), assignPlate.plate];
      saveKnownPlates(updated);
      setAssignPlate(null);
    },
    [assignPlate, buildKnownPlatesWithoutPlate, saveKnownPlates],
  );

  const handleRemoveName = useCallback(
    (summary: PlateSummary) => {
      const current = config?.lpr?.known_plates ?? {};
      const hasExactEntry = Object.values(current).some((namePlates) =>
        (namePlates ?? []).includes(summary.plate),
      );

      if (!hasExactEntry) {
        // the name matched via a regex or match distance, so there is no
        // exact entry that can be removed safely from here
        toast.info(t("toast.info.patternMatchedPlate"), {
          position: "top-center",
        });
        return;
      }

      saveKnownPlates(buildKnownPlatesWithoutPlate(summary.plate));
    },
    [buildKnownPlatesWithoutPlate, config, saveKnownPlates, t],
  );

  if (!config) {
    return <ActivityIndicator />;
  }

  if (!config.lpr?.enabled) {
    return (
      <div className="flex size-full flex-col items-center justify-center p-4 text-center">
        <LuCar className="mb-3 size-8 text-secondary-foreground" />
        <div className="text-primary">{t("lprDisabled")}</div>
      </div>
    );
  }

  return (
    <div className="flex size-full flex-col p-2">
      <Toaster />

      <div className="flex flex-col items-center justify-between gap-2 md:flex-row">
        <div className="flex items-center gap-2 text-lg text-primary">
          <LuCar className="size-5" />
          {t("title")}
        </div>
        <div className="flex w-full items-center gap-2 md:w-auto">
          <div className="relative w-full md:w-64">
            <LuSearch className="absolute left-2 top-1/2 size-4 -translate-y-1/2 text-secondary-foreground" />
            <Input
              className="pl-8"
              placeholder={t("search.placeholder")}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <Select
            value={sort}
            onValueChange={(value) => setSort(value as PlateSortType)}
          >
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="last_seen">{t("sort.lastSeen")}</SelectItem>
              <SelectItem value="count">{t("sort.count")}</SelectItem>
              <SelectItem value="plate">{t("sort.plate")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {!plates ? (
        <ActivityIndicator />
      ) : visiblePlates.length === 0 ? (
        <div className="flex size-full flex-col items-center justify-center text-center">
          <LuCar className="mb-3 size-8 text-secondary-foreground" />
          <div className="text-primary">
            {filter ? t("noMatchingPlates") : t("noPlates")}
          </div>
        </div>
      ) : (
        <div className="scrollbar-container mt-3 grid grid-cols-1 gap-3 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {visiblePlates.map((summary) => (
            <PlateCard
              key={summary.plate}
              summary={summary}
              onAssignName={() => setAssignPlate(summary)}
              onRemoveName={() => handleRemoveName(summary)}
            />
          ))}
        </div>
      )}

      <TextEntryDialog
        open={assignPlate != null}
        setOpen={(open) => {
          if (!open) {
            setAssignPlate(null);
          }
        }}
        title={t("assignDialog.title")}
        description={t("assignDialog.desc", { plate: assignPlate?.plate })}
        onSave={handleAssignName}
        defaultValue={assignPlate?.known_name ?? ""}
        regexPattern={/^[\p{L}\p{N}\s'_-]{1,50}$/u}
        regexErrorMessage={t("description.invalidName")}
      />
    </div>
  );
}

type PlateCardProps = {
  summary: PlateSummary;
  onAssignName: () => void;
  onRemoveName: () => void;
};

function PlateCard({ summary, onAssignName, onRemoveName }: PlateCardProps) {
  const { t } = useTranslation(["views/lprLibrary"]);
  const { data: config } = useSWR<FrigateConfig>("config", {
    revalidateOnFocus: false,
  });
  const apiHost = useApiHost();
  const navigate = useNavigate();
  const is24Hour = use24HourTime(config);

  const lastSeen = useFormattedTimestamp(
    summary.latest_time,
    is24Hour
      ? t("time.formattedTimestampMonthDayHourMinute.24hour", { ns: "common" })
      : t("time.formattedTimestampMonthDayHourMinute.12hour", { ns: "common" }),
    config?.ui.timezone,
  );

  const viewEvents = useCallback(() => {
    navigate(
      `/explore?recognized_license_plate=${encodeURIComponent(summary.plate)}`,
    );
  }, [navigate, summary.plate]);

  return (
    <div className="flex flex-col overflow-hidden rounded-lg bg-background_alt">
      <img
        className="aspect-video w-full cursor-pointer object-cover"
        loading="lazy"
        src={`${apiHost}api/events/${summary.latest_event_id}/thumbnail.webp`}
        alt={summary.plate}
        onClick={viewEvents}
      />
      <div className="flex flex-col gap-1.5 p-3">
        <div className="flex items-center justify-between">
          <div className="font-mono text-lg text-primary">{summary.plate}</div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="focus:outline-none"
                aria-label={t("plateActions")}
              >
                <HiOutlineDotsVertical className="size-5 text-secondary-foreground" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                className="cursor-pointer"
                onClick={onAssignName}
              >
                {summary.known_name
                  ? t("changeKnownName")
                  : t("assignKnownName")}
              </DropdownMenuItem>
              {summary.known_name && (
                <DropdownMenuItem
                  className="cursor-pointer"
                  onClick={onRemoveName}
                >
                  {t("removeKnownName")}
                </DropdownMenuItem>
              )}
              <DropdownMenuItem className="cursor-pointer" onClick={viewEvents}>
                {t("viewTrackedObjects")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div>
          {summary.known_name ? (
            <span className="inline-flex items-center rounded-full bg-selected/20 px-2 py-0.5 text-sm text-selected">
              {summary.known_name}
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full bg-secondary px-2 py-0.5 text-sm text-secondary-foreground">
              {t("unknownPlate")}
            </span>
          )}
        </div>
        <div className="text-sm text-secondary-foreground">
          {t("trackedObjects", { count: summary.count })}
          {summary.best_score != null &&
            ` · ${t("topScore", {
              score: Math.round(summary.best_score * 100),
            })}`}
        </div>
        <div className="flex flex-wrap gap-1 text-sm text-secondary-foreground">
          {summary.cameras.map((camera) => (
            <CameraNameLabel
              key={camera}
              className="smart-capitalize"
              camera={camera}
            />
          ))}
        </div>
        <div className="text-sm text-secondary-foreground">
          {t("lastSeen", { time: lastSeen })}
        </div>
      </div>
    </div>
  );
}
